# Idea file structure

Each Telegram message creates exactly one Markdown file.

Filename format:

```text
{idea-id}-{title-slug}.md
```

Example: `001-polymarket-order-book.md`

Files live in `ideas/`.

## Body

```md
# Title

Clean English version of the idea.

## Original Message

> Original Telegram message
```

## Media (optional)

If the message includes an image or video, the idea file references it with a relative path under `assets/`.

Image:

```md
![](assets/001-image.jpg)
```

Video:

```md
[Video](assets/001-video.mp4)
```

Media files are stored in `ideas/assets/`. Media filename = idea ID + media type + original file extension.
