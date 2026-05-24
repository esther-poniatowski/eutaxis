---
tags: []
aliases:
  - API documentation pipeline plan
index: "[Design Documentation — Methods](_index.md)"
---

# API documentation pipeline plan

A plan to introduce `sphinx-markdown-builder` as the Eutaxis API documentation generator, validated first on a sibling project that already has a working Sphinx build.

## Architectural shift from the existing scheme

The sibling projects under `Documents/work/projects/` (morpha, hermeneia, meandra, tessara, khimera, architekta, keystone, glossa, ktisma, loretex, janux, stelion, vitruv, eikon) all share the same documentation pipeline today. The proposed Eutaxis pipeline is a deliberate departure. This distinction must be understood before reading the test plan, because every later decision follows from it.

### Existing scheme (all 14 sibling projects)

Sphinx is the **single documentation pipeline** for the whole `docs/` tree:

- All prose files are written in Markdown via MyST-Parser (no `.rst` files anywhere — verified across all 14 projects).
- All prose files are also Sphinx inputs. Sphinx needs to know they exist; otherwise they emit "document isn't included in any toctree" warnings.
- Files are registered with Sphinx through `{toctree}` directives embedded in index files (verified: 1–4 such files per project).
- Sphinx builds the prose and the API together into a single HTML site.

The cost of this scheme is **broken GitHub readability**. `{toctree}` directives are MyST/Sphinx syntax that GitHub does not interpret — they render as literal fenced code blocks where a navigation list should appear. Any reader browsing the prose on GitHub sees the directive source code instead of the index.

### Proposed scheme (Eutaxis)

Sphinx is narrowed to a **single, isolated job**: extracting docstrings from `src/eutaxis/` and emitting them as Markdown into `docs/api/`. Sphinx never sees the prose tree.

The prose tree (`docs/guide/`, `docs/adr/`, `docs/internals/`, `docs/open-questions/`, `docs/prompt-writing-methods/`) becomes hand-written Markdown only:

- No `{toctree}` directives — replaced by plain Markdown lists.
- No `:ref:` / `:doc:` cross-reference roles — replaced by plain `[name](path.md)` links.
- Fully GitHub-readable as source files; no build step required to read the prose.

The API tree, populated by `sphinx-markdown-builder` from docstrings, is also Markdown — so the prose can link into it using normal Markdown links (`[InstructionGenerator](api/instructions.md)`).

### What is gained, what is given up

**Gained.** Prose is browsable directly on GitHub without a hosted site. The `{toctree}` literal-code-block problem disappears entirely from the prose tree. Sphinx still produces a real API reference from docstrings.

**Given up.** Sphinx's build-time validation no longer protects the prose tree:

- Broken Markdown links between prose files (or from prose to the API tree) will not surface as warnings — they fail silently on render.
- Renames in the API tree (driven by docstring changes) can silently break links from the prose tree.
- Cross-reference roles (`:ref:`, `:doc:`) are unavailable across the prose / API boundary, because Sphinx does not know the prose files exist.

This trade-off is the central design choice. The plan below assumes it has been accepted.

### Why this distinction was not visible earlier

Earlier discussion focused on whether `sphinx-markdown-builder` could parse NumPy-style docstrings (it can, via Napoleon). That confirmed the *tool* works. The remaining question — *what subset of the docs Sphinx covers* — was not stated explicitly until now. The proposed scheme uses the builder on the API alone, which is what makes the GitHub-readable prose tree possible.

## Test plan

The plan is staged from cheapest signal to most committed action. Each stage produces a decision: continue, fix, or fall back.

### Why pilot on a sibling project first

Eutaxis has three unknowns simultaneously: no `conf.py`, no Sphinx extras declared in `pyproject.toml`, and `{toctree}` directives in the prose tree that have never been validated by a Sphinx build. Adding `sphinx-markdown-builder` on top of those unknowns would conflate failure modes.

Morpha (or any sibling) has a clean baseline: a working `conf.py` with `sphinx.ext.napoleon` already enabled and `napoleon_numpy_docstring = True`, NumPy-style docstrings in `src/`, and a presumably working HTML build. Adding the Markdown builder to a known-good pipeline isolates it as the only new variable.

### Stage 1 — Confirm baseline Sphinx + Napoleon build on a sibling

Pick **morpha** as the pilot.

```bash
/Users/eresther/miniconda3/bin/conda run -n morpha-dev \
    pip install sphinx sphinx_rtd_theme myst_parser
/Users/eresther/miniconda3/bin/conda run -n morpha-dev \
    sphinx-build -W -b html docs docs/_build/html
```

> [!CHECK] Pass condition
> The HTML build completes with no warnings (warnings-as-errors via `-W`). Open `docs/_build/html/index.html` and confirm the API reference pages contain rendered NumPy parameter sections.

If this fails, the baseline itself is broken. Fix it before proceeding — adding the Markdown builder will not help.

### Stage 2 — Add `sphinx-markdown-builder` as a parallel builder

Install the actively maintained fork. Verify after install that the homepage points at `liran-funaro/sphinx-markdown-builder`, not the archived `clayrisser` original.

```bash
/Users/eresther/miniconda3/bin/conda run -n morpha-dev \
    pip install sphinx-markdown-builder
/Users/eresther/miniconda3/bin/conda run -n morpha-dev \
    pip show sphinx-markdown-builder | grep -i home
```

Edit `projects/morpha/docs/conf.py` to register the extension:

```python
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.autosummary",
    "myst_parser",
    "sphinx_markdown_builder",  # added
]
```

Build with the `markdown` target alongside the existing HTML target:

```bash
/Users/eresther/miniconda3/bin/conda run -n morpha-dev \
    sphinx-build -b markdown docs docs/_build/markdown
```

> [!NOTE] HTML output remains the ground truth
> Both builders run against the same `conf.py`. The HTML output is the reference rendering; the Markdown output is what gets evaluated. Keep both configured permanently — there is no cost to coexistence.

### Stage 3 — Evaluate output quality

Open `docs/_build/markdown/` and scan three to four representative pages: one module-level page, one class-heavy page, one page with extensive cross-references, the API index.

| Aspect                                                         | Acceptable rendering                                          | Failure mode                                |
| -------------------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------- |
| NumPy `Parameters` sections                                    | Definition list or table                                      | Verbatim reST `:param:` lines               |
| `Returns` / `Yields` sections                                  | Clean labeled paragraphs                                      | Stray colons, missing labels                |
| Type hints (`autodoc_typehints = "description"`)               | Inline next to parameter name                                 | Lost or duplicated                          |
| Sphinx cross-reference roles (`:class:`, `:func:`, `:meth:`)   | Resolved as Markdown links                                    | Literal text `` :class:`foo` ``             |
| Class hierarchies (`show-inheritance`)                         | Readable inheritance line                                     | Garbled or missing                          |
| `autosummary` tables                                           | Markdown tables with working links                            | Empty cells or broken layout                |
| GitHub renderability                                           | Push to a branch, open one output file in the GitHub web UI — frontmatter, tables, links all render | Frontmatter malformed; tables broken        |

> [!WARNING] Two lossy conversions in series
> The pipeline is `NumPy docstring → Napoleon → reST → Sphinx doctree → Markdown`. Each conversion can lose fidelity. Parameter tables and Sphinx cross-reference roles are the most likely casualties.

### Stage 4 — Decision

| Output quality                                | Decision                                                                                                            |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Acceptable as-is                              | Adopt the builder on morpha; proceed to Stage 5 (replicate on Eutaxis)                                              |
| Minor cleanup needed (e.g. `sed` rewrites)    | Adopt with a wrapper script; document the post-processing; proceed to Stage 5                                       |
| Unusable (cross-references broken, parameter tables mangled) | Fall back: either keep HTML hosted on GitHub Pages, or revisit handsdown and accept the cost of converting docstrings from NumPy to PEP 257 / Google |

### Stage 5 — Replicate on Eutaxis

This stage runs only if Stage 4 returned an "adopt" decision. The migration is mechanical once the morpha output is validated.

1. Add Sphinx dependencies to `pyproject.toml` under the `dev` extras:

   ```toml
   [project.optional-dependencies]
   dev = [
       "pytest",
       "pytest-cov",
       "mypy",
       "types-pyyaml",
       "sphinx",
       "myst-parser",
       "sphinx-rtd-theme",
       "sphinx-markdown-builder",
   ]
   ```

2. Copy `projects/morpha/docs/conf.py` into `vendor/eutaxis/docs/conf.py`. Adjust:

   - `project`, `author`, `release` to Eutaxis values
   - `sys.path.insert` to point at `../src`
   - `exclude_patterns` to exclude the prose subdirectories so Sphinx ignores them:

     ```python
     exclude_patterns = [
         "_build", "Thumbs.db", ".DS_Store",
         "guide/**",
         "adr/**",
         "internals/**",
         "open-questions/**",
         "prompt-writing-methods/**",
         "index.md",
     ]
     ```

3. Create a minimal `docs/api/index.md` (Sphinx's entry point for the API subtree) with `autosummary` or explicit `automodule` directives covering `eutaxis.instructions` and other public modules. The existing `docs/api/instructions.md` becomes the model.

4. Build:

   ```bash
   /Users/eresther/miniconda3/bin/conda run -n geonexus \
       sphinx-build -b markdown vendor/eutaxis/docs vendor/eutaxis/docs/_build/markdown
   ```

5. Inspect output, commit generated files alongside hand-written prose.

6. Add a Makefile or script wrapping the build so regeneration is one command.

### Stage 6 — Strip `{toctree}` from Eutaxis prose

Independent of the API pipeline. The five Eutaxis prose index files currently contain `{toctree}` directives that render as literal code blocks on GitHub:

- `docs/index.md`
- `docs/adr/_index.md`
- `docs/internals/_index.md`
- `docs/open-questions/_index.md`
- `docs/prompt-writing-methods/_index.md`

In the proposed scheme these directives no longer serve any purpose (Sphinx does not see these files). Replace each toctree with a plain Markdown bullet list of the same links. This step is safe to do at any time independently of the Sphinx work — it only removes broken-on-GitHub rendering.

## Portability to sibling projects

The proposed scheme applies identically to all 14 sibling projects: Sphinx narrowed to the API, prose tree freed of `{toctree}` and `:ref:` / `:doc:`. The same trade-off (lose build-time link validation for prose, gain GitHub readability) applies.

> [!IMPORTANT] Pilot scope
> This plan migrates Eutaxis only. Sibling projects remain on the existing Sphinx-everywhere scheme until lived experience with Eutaxis confirms or rejects the trade-off. The migration pattern is intentionally portable, but the rollout decision is deferred.

## Build commands reference

Both builders, kept permanently configured:

```makefile
.PHONY: docs-html docs-md docs

docs-html:
	sphinx-build -W -b html docs docs/_build/html

docs-md:
	sphinx-build -W -b markdown docs docs/_build/markdown

docs: docs-md
```

`docs-html` is useful for local preview during docstring authoring. `docs-md` produces the artifacts that get committed alongside the hand-written prose.

---

> [!LINKS] Related
> [Architecture](architecture.md)
> [Audits](audits.md)
