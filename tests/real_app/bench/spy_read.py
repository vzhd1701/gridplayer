"""What a py-spy raw file says: how much of the time the GIL was held, by which thread, doing what."""

import collections
import re
import sys

path, rate, seconds = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])

threads = collections.Counter()
leaves = collections.Counter()
files = collections.Counter()
total = 0

for line in open(path):
    line = line.rstrip()
    if not line:
        continue
    stack, count = line.rsplit(" ", 1)
    count = int(count)
    frames = stack.split(";")
    name = frames[0]
    name = re.sub(r"thread \(0x[0-9A-Fa-f]+\)", "unnamed", name)
    name = re.sub(r"^\"?(.*?)\"?$", r"\1", name)
    if "MPVEventHandler" in name:
        name = "mpv event thread"
    threads[name] += count
    total += count
    leaf = frames[-1]
    leaves[leaf] += count
    for frame in frames[1:]:
        m = re.search(r"\((.*?):\d+\)", frame)
        if m and "gridplayer" in m.group(1):
            pass
    # the first frame from the app, deepest first
    for frame in reversed(frames[1:]):
        if "gridplayer" in frame and "mpv.py" not in frame:
            files[frame] += count
            break

possible = rate * seconds
print(
    f"samples {total}, of {possible:.0f} possible: GIL held {total / possible * 100:.1f}% of the time"
)
print("by thread:")
for name, count in threads.most_common(10):
    print(f"  {count / possible * 100:5.1f}%  {name}")
print("by function, innermost:")
for name, count in leaves.most_common(14):
    print(f"  {count / possible * 100:5.1f}%  {name}")
print("by the app's innermost function:")
for name, count in files.most_common(14):
    print(f"  {count / possible * 100:5.1f}%  {name}")
