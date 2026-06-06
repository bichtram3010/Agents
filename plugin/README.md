# Plugin: Odoo Fashion & Cosmetics Multi-Agent

Plugin Claude Code cung cấp 4 subagent + 3 skill + 3 slash command để vận hành shop thời trang + mỹ phẩm trên Odoo.

## Cấu trúc

```
plugin/
├── plugin.json          # Metadata của plugin
├── mcp.json             # Cấu hình Odoo MCP server
├── agents/              # Subagent definitions (.md có YAML frontmatter)
│   ├── product-manager.md
│   ├── sales-order.md
│   ├── inventory.md
│   └── analytics.md
├── skills/              # Domain skills (SKILL.md)
│   ├── odoo-product-sync/
│   ├── odoo-sales-pipeline/
│   └── odoo-inventory-report/
└── commands/            # Slash commands
    ├── import-products.md
    ├── low-stock-alert.md
    └── sales-dashboard.md
```

## Cài đặt vào Claude Code (manual)

1. Copy nội dung `plugin/agents/*.md` vào `~/.claude/agents/`.
2. Copy `plugin/skills/*/` vào `~/.claude/skills/`.
3. Copy `plugin/commands/*.md` vào `~/.claude/commands/`.
4. Merge `plugin/mcp.json` vào `~/.claude/mcp_servers.json` (hoặc dùng `claude mcp add`).
5. Set env vars `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_PASSWORD`.

## Sử dụng

Trong Claude Code:
- `/import-products` — chạy quy trình bulk import.
- `/low-stock-alert` — báo cáo sản phẩm sắp hết hàng.
- `/sales-dashboard` — dashboard doanh số.
- Hoặc gọi subagent qua Task tool: `Use the product-manager subagent to list all fashion products`.

## Tham chiếu

- Agno (multi-agent framework): https://docs.agno.com
- CopilotKit (frontend): https://docs.copilotkit.ai
- Claude Code subagents: https://docs.claude.com/en/docs/claude-code/sub-agents
- Claude Code plugins: https://docs.claude.com/en/docs/claude-code/plugins
