# System

Telegram
↓
Capture Layer
↓
Normalization
Raw → English Idea
↓
Store
Canonical Idea + Source provenance
↓
Wiki Maintainer
↓
Ideas + Links + Topics
↓
Markdown Wiki
↓
Optional Obsidian

## Capture

Telegram is the capture interface.

A message containing a post idea enters the system as raw input. That exact text is later stored as the Idea’s Source.

## Normalization

The LLM converts the input into:

- a concise descriptive English title
- a clean grammatical English expression of the idea

Meaning is preserved during normalization.

The resulting English title and body are the canonical Idea. Source is not rewritten into the body.

## Store

Each Idea is one Markdown file under `ideas/`.

A stored Idea always includes:

- YAML Properties (`id`, `title`, `type`, `created`, `source`, `tags`)
- H1 title (the canonical English title)
- clean English Idea body
- Source (exact original Telegram text or caption)

Topics and Related Ideas sections are optional. They are added when the Wiki Maintainer creates those relationships.

Properties are structured metadata for Obsidian. Tags are lightweight filters. They do not replace Topics.

## Wiki Maintainer

The LLM maintains the wiki as new Ideas arrive.

It uses the canonical English Idea for organization and linking. Source is provenance only.

For each Idea it determines:

- where the Idea belongs
- which Topics it relates to
- which existing Ideas are meaningfully related
- which links should exist
- whether the Topic structure needs to evolve
- how the index should reflect the current wiki

The goal is a coherent wiki rather than a growing directory of disconnected notes.

## Knowledge Model

IDEA ←→ IDEA
  \       /
   \     /
    TOPIC

**Idea**

A canonical post concept: English title, English body, Properties, and Source provenance.

Each Idea remains an independent unit.

**Topic**

An organizational node connecting related Ideas. Topics are wiki files, not tags.

**Tags**

Concise semantic labels on an Idea’s Properties. Used for classification and filtering. Tags do not replace Topics.

**Related Ideas**

Direct semantic Idea-to-Idea relationships, expressed as portable Markdown links.

**Links**

Explicit relationships that allow Ideas and Topics to form an interconnected wiki. Use portable standard Markdown links only.

**Source**

The exact original Telegram text or caption. Provenance and reference, not the canonical Idea.

## Human Interface

The knowledge base is the Markdown tree under `knowledge-base/`. A local process writing those files is enough.

One production pattern is a VPS wiki synchronized one-way to a Mac and opened as an Obsidian vault:

VPS Wiki → rsync → Mac Wiki → Obsidian

Obsidian is optional. Markdown remains the portable source format.
