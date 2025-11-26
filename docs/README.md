# Documentation

This directory contains the MkDocs documentation source files.

## Local Development

Install documentation dependencies:

```bash
uv sync --group docs
```

Serve the documentation locally:

```bash
mkdocs serve
```

The documentation will be available at http://127.0.0.1:8000

## Building

Build the static site:

```bash
mkdocs build
```

The built site will be in the `site/` directory.

## Deployment

Documentation is automatically built and deployed to GitHub Pages when changes are pushed to the `main` branch.

## Structure

```
docs/
├── index.md                 # Home page
├── getting-started.md       # Quick start guide
├── guide/                   # User guides
│   ├── setup-flow.md
│   ├── device-patterns.md
│   ├── configuration.md
│   ├── discovery.md
│   └── driver.md
├── api/                     # API reference (auto-generated)
│   ├── driver.md
│   ├── device.md
│   ├── setup.md
│   ├── config.md
│   └── discovery.md
├── migration-guide.md       # Migration guide
└── contributing.md          # Contributing guide
```

## Adding Content

### User Guides

User guides are written in Markdown and placed in the `guide/` directory.

### API Reference

API reference pages use mkdocstrings to auto-generate documentation from docstrings:

```markdown
## MyClass

::: ucapi_framework.module.MyClass
    options:
      show_root_heading: true
      show_source: false
```

### Code Examples

Use fenced code blocks with syntax highlighting:

````markdown
```python
from ucapi_framework import BaseIntegrationDriver

class MyDriver(BaseIntegrationDriver):
    pass
```
````

### Admonitions

Use admonitions for notes, tips, and warnings:

```markdown
!!! note
    This is a note.

!!! tip
    This is a helpful tip.

!!! warning
    This is a warning.
```

### Tabs

Use tabs for alternative approaches:

```markdown
=== "Option 1"
    Content for option 1

=== "Option 2"
    Content for option 2
```
