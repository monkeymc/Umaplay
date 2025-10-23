Remember to read the sops

## Notebook prototyping workflow
- When explicitly asked to prototype or “start in Jupyter”, **do not touch `.py` files** (new or existing) until the user requests the migration. All draft logic must live in the notebooks.
- Begin experiments in `dev_nav.ipynb` or `dev_play.ipynb`, depending on context, even if faster to write raw `.py` edits.
- Place every prototype inside a `## PROTOTYPE` section. Each cell must start with a comment naming the destination module (e.g., `# core/actions/roulette.py`) so the user can copy/paste later.
- Before making changes, copy the current contents of the target `.py` module into the notebook cell so edits happen there first; comment imports as needed to keep the cell runnable.
- It is okay to comment out or duplicate imports temporarily inside the notebook while co-developing multiple modules.
- After validation, wait for the user to request migration before writing the finalized code into `.py` files; the user performs the copy step.
- Even if a prototype looks complete, pause and ask for explicit approval before creating or modifying any `.py` file; keep working inside the notebook until the user confirms.
- Jupyter Notebook is just a helper for me, it's a utility to quickly execute this code but at the end I will be just doing copy-paste in the new files. I will not ask you to generate the new files, probably, because I can do that manually. Use real names in implementations, don't use for example MymodulePrototype or something like that. 