# Demo video

Records and cuts the 2-minute demo of `docs/demo_video_script.md` from a running instance.
Needs ffmpeg, macOS `say` and Playwright's Chromium (`uv run --with playwright playwright install chromium`).

1. Follow the script's preparation checklist: a freshly loaded database, the live summary of
   9C_197/2026 pre-warmed, the agent checked. Then start the app, e.g.
   `DB_PATH=/tmp/rec.db uv run suva serve --port 8090`.
2. Record the clips (one per shot part; the waits for the live summary and the agent are cut):

   ```sh
   uv run --with playwright python scripts/demo_video/record.py --base-url http://127.0.0.1:8090 OUT
   ```

   It prints the agent's answer and saves it to `OUT/agent_answer.txt`: read it before using
   the video. Recording 9C_197/2026 summarises it, so reload the database before recording again.
3. Cut the video:

   ```sh
   uv run --with playwright python scripts/demo_video/build.py OUT
   ```

   This writes `Praecedens_demo.mp4` (placeholder voice from `say`), `Praecedens_demo_silent.mp4`,
   `voice_synth.m4a`, `voiceover_timing.md`, and copies `assemble.sh` and this README to `OUT`.

## Your own voice-over

Record the lines of `voiceover_timing.md` while `Praecedens_demo_silent.mp4` plays, each when its
shot starts, save the take as `voice.m4a` next to the video (any format ffmpeg reads works), then:

```sh
./assemble.sh voice.m4a
```

It replaces `Praecedens_demo.mp4` with the silent video plus your track (the video sets the
length; a shorter take is padded with silence).
