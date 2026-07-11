# Cole Medin - AI-Coding Knowledge Bundle

A portable knowledge base of my best AI-coding videos - **Claude Code, context engineering, the PIV loop, the AI layer, and the new Archon harness builder** - in the **Open Knowledge Format (OKF)**: plain markdown any AI agent can read.

## How to use it

Paste this to your AI coding assistant (Claude Code, Cursor, Codex, Gemini CLI, …):

```
Here's a knowledge bundle: https://github.com/coleam00/cole-medin-ai-coding
Read its README and set it up so I can search over it. Then tell me what's inside.
```

That's it - your agent reads the rest of this README, clones the bundle, and you can start asking questions about anything I teach.

---

## Agent setup instructions

You're being asked to make this knowledge bundle available so the user can ask questions about Cole Medin's AI-coding content. Follow these steps.

### 1. What this is

This repo is an [Open Knowledge Format (OKF)](https://github.com/GoogleCloudPlatform/knowledge-catalog) bundle - a folder of markdown files, each with a small YAML frontmatter block, navigated via `index.md`. You read it **directly**: no database, no embeddings, no API, no special tooling. It also ships a tiny, dependency-free CLI - `okf-cli.py` (Python standard library only) - for fast navigation and search.

### 2. Set it up

Clone the repo into the current working directory:

```bash
git clone https://github.com/coleam00/cole-medin-ai-coding
cd cole-medin-ai-coding
python okf-cli.py index      # confirm it works - prints the table of contents
```

### 3. Use the CLI

- `python okf-cli.py index [subpath]` - print an index (start at the root; e.g. `python okf-cli.py index videos`)
- `python okf-cli.py find "<query>"` - ranked keyword search across the bundle
- `python okf-cli.py read <path>` - print a page, e.g. `python okf-cli.py read concepts/the-piv-loop`

(You can also just open the markdown files directly - `okf-cli.py` is only a convenience.)

### 4. How to answer the user's questions

1. `python okf-cli.py find "<the user's topic>"` (or read `index.md`) to locate the relevant pages.
2. `python okf-cli.py read` the specific `videos/<slug>` or `concepts/<slug>` pages - only what's relevant, not the whole bundle (progressive disclosure).
3. Follow the relative markdown links between a video and the concepts it teaches.
4. Answer grounded in those pages, and **cite the source video** by its title and `resource` (YouTube URL) from the frontmatter.

This is read-only reference knowledge - don't modify the bundle.

## What's inside

- `index.md` - the table of contents (start here)
- `videos/` - one page per video (summary, key ideas, tools, link)
- `concepts/` - the cross-cutting themes that tie the videos together
- `okf-cli.py` - the dependency-free navigation/search CLI
- `log.md` - change history

Channel: https://www.youtube.com/@ColeMedin
