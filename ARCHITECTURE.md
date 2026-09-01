# System

Telegram
↓
Capture Layer
↓
Normalization
Raw → English Idea
↓
Wiki Maintainer
↓
Ideas + Links + Topics
↓
Markdown Wiki
↓
rsync / Mac
↓
Obsidian

## Capture

Telegram is the capture interface.

A message containing a post idea enters the system as temporary raw input.

## Normalization

The LLM converts the input into:

- a concise descriptive English title
- a clean grammatical English expression of the idea

Meaning is preserved during normalization.

The resulting English Idea becomes canonical.

## Wiki Maintainer

The LLM maintains the wiki as new Ideas arrive.

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

A canonical post concept.

Each Idea remains an independent unit.

**Topic**

An organizational node connecting related Ideas.

Topics emerge and evolve as the collection grows.

**Links**

Explicit relationships that allow Ideas and Topics to form an interconnected wiki.

## Human Interface

The live knowledge base resides on the VPS.

It is synchronized one-way to the Mac and opened as an Obsidian vault.

VPS Wiki → rsync → Mac Wiki → Obsidian

Obsidian is an interface over the Markdown wiki, not the storage format itself.
