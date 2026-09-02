# Idea Dump wiki schema

Idea Dump is a living LLM Wiki for post ideas.

This file defines the wiki’s structure, concepts, and maintenance rules for the LLM.

## Purpose

Capture post ideas in any language, normalize them into canonical English Ideas, store them as Markdown with Source provenance, and keep the collection coherent as it grows.

Telegram is the capture interface. The wiki’s product is Post Ideas and their organization.

Obsidian is the primary human interface. Markdown remains the portable source format.

## Idea

An Idea is a canonical post concept.

One Idea represents one distinct post concept.

One Idea = one Markdown file under `ideas/`.

Ideas keep their individual identity even when they are related to other Ideas or Topics.

### Canonical file

Required, in this order:

1. YAML Properties
2. H1 title (canonical English title)
3. Clean English Idea body
4. Source

Optional, after the body and before Source:

- Topics
- Related Ideas

Media associated with the Idea may appear with the body using portable relative Markdown links into `assets/`.

The Wiki Maintainer may use the canonical English Idea for organization and linking. It must not treat Source as the Idea body.

### Properties

YAML front matter. Structured metadata for Obsidian.

| Field | Rule |
| --- | --- |
| `id` | Quoted zero-padded Idea ID |
| `title` | Canonical English title |
| `type` | Always `idea` |
| `created` | Creation date (`YYYY-MM-DD`) |
| `source` | Always `telegram` for Telegram captures |
| `tags` | Zero or more concise semantic tags |

Do not add `status`, `updated`, or other workflow metadata.

**Tags** are lightweight classification and filtering. They do not replace Topics.

### Source

The `## Source` section preserves the exact original Telegram text or caption, verbatim.

Source is provenance and reference. It is not the canonical Idea body.

### Example

```markdown
---
id: "015"
title: Vietnam Enters Winter Season
type: idea
created: 2026-09-01
source: telegram
tags:
  - vietnam
  - seasons
---

# Vietnam Enters Winter Season

We are gradually entering the winter season in Vietnam.

## Topics

- [Seasons](../topics/seasons.md)

## Related Ideas

- [Another Idea](012-another-idea.md)

## Source

> vietnamda yavas yavas kis sezonuna giriyoruz
```

Topics and Related Ideas appear only when those relationships exist.

## Topic

A Topic is an organizational wiki node.

Topics connect related Ideas. Topics are not Post Ideas. Tags are not Topics.

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
- may assign tags as lightweight classification
- identifies relevant Topics
- identifies meaningfully related Ideas
- maintains appropriate links
- evolves Topic structure when necessary
- keeps `index.md` coherent as the entry point to Ideas and Topics
- records wiki changes in `log.md`

The maintainer uses the canonical English Idea for organization and linking. Source stays verbatim.

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
