import os, random
import json
import time
import requests
from obswebsocket import obsws
from obswebsocket import requests as orequests
from pygame import mixer
import threading
import Queue

def get_difference(a, b):
    s = set(a)
    return [x for x in b if x not in s]


def get_last_modified_file_path(directory):
    files = []
    for file in os.listdir(str(directory)):
        if file == "Status.json":
            continue
        files.append(dict(file=file, timestamp=os.stat(os.path.join(str(directory), file)).st_mtime))
    last_modified_files = sorted(
        files,
        key=lambda x: x['timestamp'],
        reverse=True
    )
    return os.path.join(str(directory), last_modified_files[0]['file'])


class JournalWatcher(object):
    def __init__(self, directory, watch_delay=0.1):
        self._directory = str(directory)
        self._watch_delay = watch_delay
        self._journal_files = os.listdir(self._directory)
        self._current_file_path = get_last_modified_file_path(self._directory)

    def watch_latest_file(self):
        print "Reading file at path: {}".format(self._current_file_path)
        with open(self._current_file_path, 'r') as journal_file:
            # Go to the end of the file
            print('Seeking to the end of the journal file')
            journal_file.seek(0, 2)
            while True:
                new_file_path = self.get_new_journal_file()
                # stop looping if a new journal has been detected
                if new_file_path:
                    print('Switching to file: {}'.format(new_file_path))
                    self._current_file_path = new_file_path
                    break
                line = journal_file.readline()
                if line and not line == '\n':
                    yield line
                time.sleep(self._watch_delay)

    def get_new_journal_file(self):
        files = os.listdir(self._directory)
        if not sorted(files) == sorted(self._journal_files):
            new_files = get_difference(self._journal_files, files)
            # Update the files seen by the class
            self._journal_files = files
            # Checking the length takes deletions into consideration
            if len(new_files):
                new_file = new_files[0]
                print('New journal file detected: {}'.format(new_file))
                return new_file
        return None


class MusicRunner(threading.Thread):
    def __init__(self, queue):
        threading.Thread.__init__(self)
        self.queue = queue

    def run(self):
        while True:
            file_name = self.queue.get()
            if mixer.music.get_busy():
                print("fading out")
                mixer.music.fadeout(3000)
            mixer.music.load(file_name)
            mixer.music.play()
            mixer.music.set_volume(0)
            print("playing {}").format(file_name)
            while mixer.music.get_volume() < 1:
                mixer.music.set_volume(mixer.music.get_volume() + .05)
                print("volume is {}").format(str(mixer.music.get_volume()))
                time.sleep(.1)

            self.queue.task_done()


def main():
    host = "localhost"
    port = 4444
    password = "secret"
    ws = obsws(host, port, password)
    try:
        ws.connect()
    except Exception:
        pass
    else:
        scenes = ws.call(orequests.GetSceneList()).getScenes()
        scene_list = []
        for thing in scenes:
            scene_list.append(thing['name'])

    j = JournalWatcher(directory="C:\\Users\\danho\\Saved Games\\Frontier Developments\\Elite Dangerous")

    mixer.init()
    music_queue = Queue.Queue()
    music_runner = MusicRunner(music_queue)
    music_runner.start()
    while True:
        for event in j.watch_latest_file():
            d = json.loads(event)
            print json.dumps(d, indent=2)

            # Do we want any music for this event? If so, queue it up
            music_dir = d["event"]
            if d["event"] == "StartJump" and d["JumpType"] == "Hyperspace":
                music_dir += "\\Hyperspace"
            elif d["event"] == "SupercruiseExit" and d["BodyType"] == "Station":
                music_dir += "\\Station"
            try:
                music_selection = [os.path.join(music_dir, f) for f in os.listdir(music_dir)
                                   if os.path.isfile(os.path.join(music_dir, f))]
            except Exception:
                music_selection = []
            dir_length = len(music_selection)
            if dir_length == 0:
                print("No music for event")
            else:
                music_queue.put(random.choice(music_selection))
                print("Queueing up {}").format(music_selection)

            # Post events to API and let OBS show something
            try:
                post_event(d["event"], d)
            except Exception:
                pass
            else:
                time.sleep(2)
                if d["event"] in scene_list:
                    try:
                        ws.call(orequests.SetCurrentScene(d["event"]))
                    except Exception:
                        pass
                    else:
                        time.sleep(5)
                        try:
                            ws.call(orequests.SetCurrentScene("Game"))
                        except Exception:
                            pass
            #print('Event detected: {}'.format(event))

def post_event(type, data):
    url = 'http://127.0.0.1:5000/{}'.format(type)
    payload = data
    headers = {'content-type': 'application/json'}
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    print response


if __name__ == "__main__":
    main()
