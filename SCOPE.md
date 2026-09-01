# Scope

Idea Dump maintains a living wiki of post ideas.

Its responsibility is:

Capture → Normalize → Store → Connect → Organize → Maintain

The fundamental unit of the system is the Post Idea.

A Post Idea begins as a rough Telegram input and becomes a canonical English Idea in the wiki.

The system preserves individual Ideas while continuously organizing their relationships through Topics and links.

The result is an increasingly structured and navigable collection of post ideas that can be explored through Obsidian.

## Wiki Structure

```text
knowledge-base/
├── schema.md
├── index.md
├── log.md
├── ideas/
│   └── ...
├── topics/
│   └── ...
└── assets/
    └── ...
```

### schema.md

Defines the wiki's structure, concepts, and maintenance rules for the LLM.

### index.md

The main entry point into the wiki.

Provides navigation into the current collection of Ideas and Topics.

### log.md

Chronological record of wiki changes.

### ideas/

Contains canonical Post Ideas.

One Idea = one distinct post concept.

### topics/

Contains organizational pages connecting related Ideas.

Topics are maintained dynamically as the Idea collection evolves.

### assets/

Contains media associated with Ideas.
