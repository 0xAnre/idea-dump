# Scope

Idea Dump maintains a living wiki of post ideas.

Its responsibility is:

Capture → Normalize → Store → Connect → Organize → Maintain

The fundamental unit of the system is the Post Idea.

A Post Idea begins as a rough Telegram input. The wiki stores a canonical English Idea plus the original Telegram text as Source provenance.

The system preserves individual Ideas while continuously organizing their relationships through Topics and links.

Tags on an Idea are lightweight classification only. They do not replace Topics.

The result is an increasingly structured and navigable collection of post ideas. Markdown is the portable source format. Obsidian is an optional interface over those files.

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

One Idea = one distinct post concept = one Markdown file.

Every Idea file includes YAML Properties, an H1 title, the clean English body, and a Source section. Topics and Related Ideas sections are optional.

### topics/

Contains organizational pages connecting related Ideas.

Topics are maintained dynamically as the Idea collection evolves.

### assets/

Contains media associated with Ideas.
