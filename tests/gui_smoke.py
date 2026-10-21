import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import scriptsync_gui as g
T = sys.argv[1]; shot = sys.argv[2]
app = g.App()
app.update()
app.add_clips = None
app._add_entry(os.path.join(T, "testclip.mp4"), os.path.join(T, "testclip.txt"))
app._add_entry(os.path.join(T, "other.mp4"), None)      # no script -> should be flagged, not run
app._after_add(); app.update()
pass
app.var_out.set("")
app.start()
t0 = time.time()
while app._busy() or not app.q.empty():
    app.update(); time.sleep(0.02)
    if time.time() - t0 > 60: print("TIMEOUT"); break
for _ in range(20): app.update(); time.sleep(0.02)
first = next(iter(app.entries))
app.tree.selection_set(first); app.update()
for _ in range(10): app.update(); time.sleep(0.02)
print("rows:", [app.tree.item(i, "values") for i in app.tree.get_children()])
print("cues shown:", len(app.ctree.get_children()), "|", app.summary.cget("text"))
os.system(f"import -window root {shot}")
app.destroy()
