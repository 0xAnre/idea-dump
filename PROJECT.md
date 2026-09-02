# Idea Dump

Idea Dump is a Karpathy-style LLM Wiki for post ideas.

It provides a frictionless way to capture post ideas as they occur and gradually builds them into an organized, interconnected collection.

Core experience:

Telegram → LLM → Living Post-Idea Wiki → Obsidian

A rough Telegram message is the capture input.

The LLM converts that input into a clean, grammatical English Post Idea while preserving its original meaning.

That English Post Idea is the canonical piece of information in the wiki.

The exact original Telegram text is stored with the Idea as Source provenance. It is a reference, not the canonical Idea.

Each Idea file also carries YAML Properties for Obsidian (including lightweight tags) and may link to Topics and Related Ideas.

Over time, the LLM maintains the wiki by organizing ideas into topics, discovering relationships between ideas, creating links, and keeping the structure coherent as the collection grows.

Obsidian is the primary human interface for browsing and navigating the wiki. Markdown remains the portable source format.

## North Star

Idea Dump captures, organizes, connects, and maintains post ideas as a living LLM wiki.

## Core Principles

**Post Ideas are the product.**

Every Idea represents a distinct post concept worth keeping.

**The clean English Idea is canonical.**

Normalization produces the title and body that the wiki treats as the Idea. Source is the original Telegram text, preserved verbatim for provenance only.

**Ideas remain independent.**

Related Ideas may be connected and organized together, but their individual meaning and identity are preserved.

**Topics and tags are different.**

Tags are lightweight classification on the Idea. Topics are real wiki pages that connect Ideas. Tags do not replace Topics.

**The wiki compounds over time.**

New Ideas do not simply accumulate as files. The LLM continuously places them within the existing network of Ideas and Topics.

**Markdown is the knowledge base.**

The wiki remains a portable collection of human-readable files. Obsidian is the primary interface over those files, not a separate storage format.
