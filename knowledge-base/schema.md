# Idea Dump wiki schema

Idea Dump is a living LLM Wiki for post ideas.

This file defines the wiki’s structure, concepts, and maintenance rules for the LLM.

## Purpose

Capture post ideas, normalize them into canonical English Ideas, store them as Markdown, and keep the collection coherent as it grows.

Telegram is only the capture interface. The wiki’s product is Post Ideas and their organization.

## Idea

An Idea is a canonical post concept.

Canonical content is:

- a concise descriptive English title
- a clean grammatical English expression of the idea

One Idea represents one distinct post concept.

Ideas keep their individual identity even when they are related to other Ideas or Topics.

Raw Telegram input is capture input only. It is not part of the wiki knowledge model.

One Idea = one Markdown file under `ideas/`.

## Topic

A Topic is an organizational wiki node.

Topics connect related Ideas. Topics are not Post Ideas.

Topics may emerge and evolve as the collection grows.

Topics organize existing Ideas. They do not develop Ideas into posts.

Topic pages live under `topics/`.

## Links

Use portable standard Markdown links only. Do not require application-specific link syntax.

Allowed relationships:

- An Idea may link to related Ideas.
- An Idea may link to Topics.
- A Topic links to its related Ideas.

Links must not merge Ideas or replace an Idea’s independent meaning.

## Wiki Maintainer

When a new canonical Idea is added, the maintainer:

- places it in the existing wiki structure
- identifies relevant Topics
- identifies meaningfully related Ideas
- maintains appropriate links
- evolves Topic structure when necessary
- keeps `index.md` coherent as the entry point to Ideas and Topics
- records wiki changes in `log.md`

The maintainer must preserve the meaning and independent identity of Ideas.

The goal is a coherent wiki, not a growing directory of disconnected notes.

## Wiki structure

```text
knowledge-base/
├── schema.md
├── index.md
├── log.md
├── ideas/
├── topics/
└── assets/
```

### schema.md

This file. Structure, concepts, and maintenance rules for the LLM.

### index.md

Main entry point into the wiki. Navigation into the current collection of Ideas and Topics.

### log.md

Chronological record of wiki changes.

### ideas/

Canonical Post Ideas. One file per distinct post concept.

### topics/

Organizational pages connecting related Ideas. Maintained as the Idea collection evolves.

### assets/

Media associated with Ideas.
