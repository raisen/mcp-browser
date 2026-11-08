"""Centralized Textual TCSS styling declarations."""

TCSS_STYLES = """
Screen {
    background: $background;
    color: $text;
}

#header-bar {
    dock: top;
    height: 1;
    background: $primary-background;
    color: $text;
    padding: 0 1;
    layout: horizontal;
}

#header-title { width: auto; text-style: bold; }
#header-stats { width: 1fr; text-align: center; color: $text-muted; }
#header-help { width: auto; text-align: right; color: $text-muted; }

#main-container {
    layout: horizontal;
    height: 1fr;
    width: 100%;
}

#server-list {
    width: 32;
    min-width: 24;
    max-width: 45;
    height: 100%;
}

#sidebar {
    width: 100%;
    height: 100%;
    border-right: solid $primary;
}

#server-search { dock: top; margin: 0; border: none; height: 3; }
#server-tree { height: 1fr; width: 100%; padding: 0; }
#server-detail { width: 1fr; height: 100%; }
#detail-container { width: 100%; height: 100%; padding: 0 1; }

#server-header {
    height: auto;
    max-height: 5;
    border-bottom: solid $primary;
    padding: 0 1;
    layout: horizontal;
}

#header-info { width: 1fr; height: auto; }
#header-title-text { text-style: bold; }
#header-sub-text { color: $text-muted; }
#header-actions { width: auto; height: auto; align: right middle; }

#detail-tabs { height: 1fr; }
TabPane { padding: 1 0; height: 1fr; }
#overview-scroll { height: 1fr; overflow-y: auto; }
.overview-section { margin-bottom: 1; }
.overview-heading { text-style: bold; color: $accent; margin-bottom: 0; }
.overview-content { color: $text; }

#tool-runner-container {
    layout: horizontal;
    height: 100%;
    width: 100%;
}

#tool-list {
    width: 26;
    min-width: 20;
    height: 100%;
    border-right: solid $surface-lighten-2;
}

#tool-detail {
    width: 1fr;
    height: 100%;
    padding-left: 1;
    overflow-y: auto;
}

#tool-args-input {
    height: 7;
    min-height: 5;
    max-height: 12;
    margin-bottom: 1;
}

#output-header-bar {
    height: auto;
    align: left middle;
    margin-top: 1;
}

#output-label {
    width: 1fr;
}

#btn-toggle-format, #btn-toggle-maximize {
    height: 1;
    min-width: 14;
    border: none;
    background: $surface;
    margin-left: 1;
}

#tool-runner.output-maximized #tool-list,
#tool-runner.output-maximized #tool-schema,
#tool-runner.output-maximized #args-label,
#tool-runner.output-maximized #tool-args-input,
#tool-runner.output-maximized #tool-actions {
    display: none;
}

#tool-output-scroll {
    height: 1fr;
    min-height: 6;
    border: solid $surface-lighten-2;
    background: $surface-darken-1;
    overflow-y: auto;
}

#tool-output-scroll:focus {
    border: solid $accent;
}

#tool-output {
    width: 100%;
    height: auto;
    padding: 0 1;
}

#resource-container, #prompt-container {
    layout: horizontal;
    height: 100%;
    width: 100%;
}

#resource-list, #prompt-list {
    width: 28;
    min-width: 20;
    height: 100%;
    border-right: solid $surface-lighten-2;
}

#resource-detail, #prompt-detail {
    width: 1fr;
    height: 100%;
    padding-left: 1;
    overflow-y: auto;
}

#resource-output-scroll, #prompt-output-scroll {
    height: 1fr;
    min-height: 6;
    border: solid $surface-lighten-2;
    background: $surface-darken-1;
    overflow-y: auto;
}

#resource-output-scroll:focus, #prompt-output-scroll:focus {
    border: solid $accent;
}

#resource-output, #prompt-output {
    width: 100%;
    height: auto;
    padding: 0 1;
}

ConfirmModal, HelpModal {
    align: center middle;
}

#confirm-dialog, #help-dialog {
    height: auto;
    max-height: 90%;
    background: $surface;
    padding: 1 2;
}

#confirm-dialog {
    width: 70;
    border: thick $warning;
}

#help-dialog {
    width: 65;
    border: thick $primary;
}

#confirm-title, #help-title {
    text-style: bold;
    text-align: center;
    margin-bottom: 1;
}

#confirm-title { color: $warning; }
#help-title { color: $primary; }

#confirm-body, #help-body {
    height: auto;
    overflow-y: auto;
    margin-bottom: 1;
}

#confirm-body { max-height: 15; }
#help-body { max-height: 18; }

#confirm-buttons, #help-buttons {
    layout: horizontal;
    align: right middle;
}
"""
