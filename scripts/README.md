# profile images

Install the renderer and rebuild the SVGs from the saved GitHub data:

```sh
python -m pip install -r scripts/requirements.txt
python scripts/profile.py
```

To fetch fresh data, authenticate the GitHub CLI with `gh auth login`, then run:

```sh
python scripts/profile.py --refresh
```

The profile lives in `README.md`. GitHub displays the SVG images directly from `assets/profile/`. Screens below 600px use separate mobile SVGs.

The profile workflow refreshes the public repository count, followers, stars, language percentages and contribution calendar daily at 03:23 UTC. It also supports manual runs. It uses the repository's built-in `GITHUB_TOKEN` and starts working once the files are pushed to `main` with Actions enabled.

Language percentages measure code bytes across public repositories owned by `sorried`, excluding forks. Archived repositories count. Up to six languages appear individually. When there are more, the top five appear individually and the rest are grouped as Other. Stars earned exclude forks. Contributions come from GitHub's contribution calendar.

The bio and stack are edited in `scripts/profile.py`. The avatar comes from `assets/avatar.png`. Font outlines and icon paths are embedded in the SVGs, so the displayed profile does not fetch fonts or icons from external services. The avatar ring, technology icons and project arrows loop. All animations respect reduced-motion preferences. Numeric values and language proportions stay fixed while the artwork animates.

The recent activity block counts contributions and active days over the last 30 calendar days. A current streak may end yesterday while today has no contributions yet. The longest streak covers the year supplied by the GitHub contribution calendar. Every project image in the README links to its repository.
