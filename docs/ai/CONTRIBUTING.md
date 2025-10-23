Remember to read the sops

## Notebook prototyping workflow
- If user request to work in some experiments or in a jupyter. Begin experiments in `dev_nav.ipynb` or `dev_play.ipynb` to iterate quickly; depending on the context.
- Place any new or modified code under a `## PROTOTYPE` cell with an initial comment naming the intended target file. Create the section if that there not exist, we need to encapsulate all necesary logic there, regardless of what is already in the jupyter notebook
- Comment out imports temporarily if multiple modules are evolving together during the notebook session.
- Once the behavior is validated, user will copy the finalized code into the corresponding `.py` files.