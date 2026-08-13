# Shadowing Trainer documentation

[简体中文](../zh-CN/README.md) | English · [Back to project home](../../README.en.md)

This directory contains the detailed Shadowing Trainer v0.4.1 user and developer documentation. The root README provides only the shortest startup path; installation, model configuration, and workflow details live here.

## Getting started

1. [Installation, upgrades, and startup](getting-started.md): prepare Python, Node.js, FFmpeg, the database, and optional Local Whisper.
2. [User guide](user-guide.md): configure languages and models, upload material, generate text, and complete a shadowing evaluation.
3. [Models and providers](providers.md): understand adapters, capabilities, formats, endpoints, and the three test levels.

## Reference

- [Multilingual behaviour](multilingual.md): language snapshots, provider language limits, segmentation, and scoring boundaries.
- [Development and API](development.md): stack, layout, data files, major endpoints, and verification commands.
- [Release history](changelog.md): major changes in v0.4.1 and earlier versions.

## Documentation conventions

- Every English page links to its Chinese counterpart, and every Chinese page links back to English.
- The Settings Provider Catalog and backend registry are the final source of truth for model support; these documents explain their behaviour.
- Commands assume the repository root as their starting point and the source directory is `shadowing/`.
