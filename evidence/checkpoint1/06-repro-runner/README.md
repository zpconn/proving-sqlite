# campaign.py builds and runs repro files (checkpoint 1, fix 2)

**The problem.** Builder-written text ran in reviewer sandboxes, which have network and the reviewer's login:
- Reviewer rule 2 said `make -C proofs/C-NN prove`, so GNU make evaluated the builder's Makefile. A line `PY := <cmd>; python3` after the include runs `<cmd>`. scan.py and prove.py reject such a Makefile, but only after make has already run it.
- Rule 8 had the reviewer build and run the builder's tests/repro files.

**Now.**
- No session runs make in a card directory. proofs/HOWTO.md, agents/builder/GOAL.md, agents/reviewer/GOAL.md and both of campaign.py's prompts give `tools/prove.py prove|coverage --card-dir proofs/C-NN [--config <name>]`. prove.py parses the Makefile declaratively, as the gate already did (gate.py).
- On a FINDING round, campaign.py builds and runs each `tests/repro/F-draft-C-NN-<k>.c` itself before it starts the reviewer (`run_repros`), against main's upstream/sqlite3.c, with one fixed command:
  `cc -std=gnu11 -g -O1 -fno-omit-frame-pointer -fsanitize=address,undefined -fno-sanitize-recover=undefined -I upstream -o repro F.c -lm -lpthread -ldl`
  and then runs the binary. A repro that is a symlink, or not a regular file, isn't built.
- Both steps run in bubblewrap:
  - `--unshare-all`, so there is no network;
  - $HOME and /mnt are hidden behind read-only tmpfs mounts;
  - `--clearenv`, with only PATH, HOME=/nonexistent and the sanitizer options set;
  - nothing is writable but its own output directory.
- The output goes to `.campaign/repro/` in the reviewer's worktree, and the reviewer's prompt lists it.
- Reviewer rule 8 says to judge from that output and not to build or run a repro. Builder rule 8 says a repro is a `main` that starts with `#include "sqlite3.c"`.

**This run.**
- `F-draft-C-15-1.c` is the bring-up probe of A-001's premise, sqlite3VdbeRecordUnpack(2, {0x02, 0x81}) on an exact-size allocation.
- It also checks the sandbox: it tries to read ~/.gitconfig, connect to 1.1.1.1:443, and open /mnt/c.
- `F-draft-C-15-1.output.txt` is what campaign.py handed over:
  - build exit 0;
  - "home readable: no", "network: no", "mnt: hidden";
  - an ASan heap-buffer-overflow READ of size 1 at upstream line 38190, called from 92137. That is the same report as evidence/bringup/08-probes.md §1.8.2.

**Tests that fail on 71447f2:**
- tool tests `-k docs` (no `make -C proofs/C-NN prove|coverage` in the instructions, and reviewer rule 8 reads campaign.py's output);
- `-k campaign` (`repro-sandboxed`);
- the selftest's two fix 2 checks: a toy repro under ASan/UBSan with $HOME unreadable and the network unreachable, a symlinked repro not built, and the reviewer prompt naming `.campaign/repro/`.
