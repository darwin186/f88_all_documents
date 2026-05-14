---
version: "alpha"
name: "F88 Documents v2"
description: "A compact operations design system for document intake, checking, packaging, KPI tracking, user monitoring, and document borrowing workflows."
colors:
  primary: "#00844A"
  primary-hover: "#006837"
  primary-strong: "#047857"
  primary-soft: "#ECFDF5"
  primary-soft-strong: "#D1FAE5"
  primary-text: "#047857"
  secondary: "#374151"
  secondary-hover: "#1F2937"
  background: "#F5F6F8"
  surface: "#FFFFFF"
  surface-muted: "#F9FAFB"
  surface-subtle: "#F3F4F6"
  border: "#E5E7EB"
  border-soft: "#F3F4F6"
  border-strong: "#D1D5DB"
  text: "#1F2937"
  text-strong: "#111827"
  text-muted: "#6B7280"
  text-subtle: "#9CA3AF"
  text-inverse: "#FFFFFF"
  success: "#10B981"
  success-hover: "#059669"
  success-soft: "#ECFDF5"
  success-border: "#A7F3D0"
  warning: "#F59E0B"
  warning-soft: "#FFFBEB"
  warning-border: "#FDE68A"
  danger: "#EF4444"
  danger-text: "#DC2626"
  danger-soft: "#FEF2F2"
  danger-border: "#FECACA"
  info: "#3B82F6"
  info-soft: "#EFF6FF"
  info-border: "#BFDBFE"
  disabled: "#F3F4F6"
  disabled-text: "#9CA3AF"
  overlay: "#00000080"
typography:
  page:
    fontFamily: "Inter, SF Pro Text, Helvetica Neue, Arial, sans-serif"
    fontSize: "10px"
    fontWeight: "400"
    lineHeight: "1.5"
    letterSpacing: "0"
  body:
    fontFamily: "Inter, SF Pro Text, Helvetica Neue, Arial, sans-serif"
    fontSize: "10px"
    fontWeight: "400"
    lineHeight: "1.5"
    letterSpacing: "0"
  body-small:
    fontFamily: "Inter, SF Pro Text, Helvetica Neue, Arial, sans-serif"
    fontSize: "9px"
    fontWeight: "400"
    lineHeight: "1.45"
    letterSpacing: "0"
  body-xsmall:
    fontFamily: "Inter, SF Pro Text, Helvetica Neue, Arial, sans-serif"
    fontSize: "8px"
    fontWeight: "400"
    lineHeight: "1.4"
    letterSpacing: "0"
  label:
    fontFamily: "Inter, SF Pro Text, Helvetica Neue, Arial, sans-serif"
    fontSize: "9px"
    fontWeight: "500"
    lineHeight: "1.4"
    letterSpacing: "0"
  label-strong:
    fontFamily: "Inter, SF Pro Text, Helvetica Neue, Arial, sans-serif"
    fontSize: "10px"
    fontWeight: "600"
    lineHeight: "1.4"
    letterSpacing: "0"
  table:
    fontFamily: "Inter, SF Pro Text, Helvetica Neue, Arial, sans-serif"
    fontSize: "10px"
    fontWeight: "400"
    lineHeight: "1.45"
    letterSpacing: "0"
  table-header:
    fontFamily: "Inter, SF Pro Text, Helvetica Neue, Arial, sans-serif"
    fontSize: "10px"
    fontWeight: "600"
    lineHeight: "1.35"
    letterSpacing: "0"
  title:
    fontFamily: "Inter, SF Pro Text, Helvetica Neue, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: "600"
    lineHeight: "1.35"
    letterSpacing: "0"
  section-title:
    fontFamily: "Inter, SF Pro Text, Helvetica Neue, Arial, sans-serif"
    fontSize: "11px"
    fontWeight: "600"
    lineHeight: "1.35"
    letterSpacing: "0"
  nav:
    fontFamily: "Inter, SF Pro Text, Helvetica Neue, Arial, sans-serif"
    fontSize: "10px"
    fontWeight: "400"
    lineHeight: "1.4"
    letterSpacing: "0"
spacing:
  "0": "0px"
  "0.5": "2px"
  "1": "4px"
  "1.5": "6px"
  "2": "8px"
  "2.5": "10px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
  "10": "40px"
  "12": "48px"
  page-padding: "32px"
  nav-padding-x: "16px"
  nav-padding-y: "12px"
  card-padding: "16px"
  filter-padding: "12px"
  input-padding-x: "12px"
  input-padding-y: "8px"
  table-cell-x: "12px"
  table-cell-y: "8px"
  toast-gap: "8px"
  toast-offset-top: "76px"
  toast-offset-right: "16px"
rounded:
  none: "0px"
  sm: "4px"
  md: "6px"
  lg: "8px"
  xl: "12px"
  "2xl": "16px"
  full: "9999px"
  card: "16px"
  panel: "16px"
  input: "12px"
  button: "8px"
  badge: "9999px"
  avatar: "0px"
shadows:
  none: "none"
  sm: "0 1px 2px 0 rgba(0, 0, 0, 0.05)"
  md: "0 4px 6px -1px rgba(0, 0, 0, 0.10), 0 2px 4px -2px rgba(0, 0, 0, 0.10)"
  lg: "0 10px 15px -3px rgba(0, 0, 0, 0.10), 0 4px 6px -4px rgba(0, 0, 0, 0.10)"
  xl: "0 20px 25px -5px rgba(0, 0, 0, 0.10), 0 8px 10px -6px rgba(0, 0, 0, 0.10)"
  toast: "0 10px 20px rgba(15, 23, 42, 0.08)"
  nav: "0 1px 2px 0 rgba(0, 0, 0, 0.05)"
elevation:
  flat:
    shadow: "{shadows.none}"
    borderColor: "{colors.border}"
  raised:
    shadow: "{shadows.sm}"
    borderColor: "{colors.border-soft}"
  dropdown:
    shadow: "{shadows.lg}"
    borderColor: "{colors.border}"
  modal:
    shadow: "{shadows.xl}"
    borderColor: "{colors.border}"
motion:
  duration-fast: "150ms"
  duration-standard: "200ms"
  duration-slow: "300ms"
  easing-standard: "cubic-bezier(0.4, 0, 0.2, 1)"
  easing-enter: "cubic-bezier(0, 0, 0.2, 1)"
  easing-exit: "cubic-bezier(0.4, 0, 1, 1)"
  toast-exit-transform: "translateY(-4px)"
layout:
  page-background: "{colors.background}"
  content-max-width: "1600px"
  content-wide-width: "1400px"
  nav-height-min: "56px"
  input-height: "34px"
  icon-size-sm: "12px"
  icon-size-md: "14px"
  drawer-width: "384px"
  modal-width-sm: "320px"
  modal-width-md: "576px"
components:
  page:
    backgroundColor: "{colors.background}"
    textColor: "{colors.text}"
    typography: "{typography.page}"
    padding: "{spacing.page-padding}"
  top-nav:
    backgroundColor: "#FFFFFFF2"
    textColor: "{colors.text-muted}"
    typography: "{typography.nav}"
    rounded: "{rounded.none}"
    padding: "{spacing.nav-padding-y}"
    shadow: "{shadows.nav}"
  top-nav-link:
    textColor: "{colors.text-muted}"
    typography: "{typography.nav}"
  top-nav-link-active:
    textColor: "{colors.primary}"
    typography: "{typography.label-strong}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.card}"
    padding: "{spacing.card-padding}"
    shadow: "{shadows.sm}"
  filter-panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "{spacing.filter-padding}"
    shadow: "{shadows.sm}"
  input:
    backgroundColor: "{colors.surface-muted}"
    textColor: "{colors.text}"
    rounded: "{rounded.input}"
    padding: "{spacing.input-padding-y}"
    height: "{layout.input-height}"
  input-focus:
    backgroundColor: "{colors.surface-muted}"
    borderColor: "{colors.primary}"
    rounded: "{rounded.input}"
  button-primary:
    backgroundColor: "{colors.primary-strong}"
    textColor: "{colors.text-inverse}"
    typography: "{typography.label-strong}"
    rounded: "{rounded.button}"
    padding: "8px 16px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.text-inverse}"
    rounded: "{rounded.button}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.label-strong}"
    rounded: "{rounded.button}"
    padding: "8px 12px"
  button-secondary-hover:
    backgroundColor: "{colors.surface-muted}"
    textColor: "{colors.text}"
    rounded: "{rounded.button}"
  button-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.danger-text}"
    typography: "{typography.label-strong}"
    rounded: "{rounded.button}"
    padding: "8px 12px"
  table:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    typography: "{typography.table}"
    rounded: "{rounded.card}"
    shadow: "{shadows.sm}"
  table-header:
    backgroundColor: "{colors.surface-muted}"
    textColor: "{colors.text-muted}"
    typography: "{typography.table-header}"
  table-row-hover:
    backgroundColor: "{colors.surface-muted}"
  badge-neutral:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.text}"
    typography: "{typography.body-small}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
  badge-success:
    backgroundColor: "{colors.success-soft}"
    textColor: "{colors.primary-text}"
    typography: "{typography.body-small}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
  badge-warning:
    backgroundColor: "{colors.warning-soft}"
    textColor: "#92400E"
    typography: "{typography.body-small}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
  badge-danger:
    backgroundColor: "{colors.danger-soft}"
    textColor: "{colors.danger-text}"
    typography: "{typography.body-small}"
    rounded: "{rounded.badge}"
    padding: "4px 8px"
  toast:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-strong}"
    typography: "{typography.body}"
    rounded: "{rounded.xl}"
    padding: "10px 12px"
    shadow: "{shadows.toast}"
  dropdown:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.xl}"
    padding: "4px"
    shadow: "{shadows.lg}"
  drawer:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.none}"
    shadow: "{shadows.xl}"
  modal:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.2xl}"
    shadow: "{shadows.xl}"
---

## Overview

F88 Documents v2 is a dense internal operations interface. The visual identity is calm, clerical, and task-focused: pale gray workspace, white work surfaces, compact controls, and a restrained F88 green accent used only for navigation state, primary actions, focus, progress, and success.

The system should feel like a back-office document control desk rather than a marketing product. Screens prioritize scanning, filtering, bulk operations, tables, drawers, and status changes. Decoration is minimal. Information density is high, but the interface remains legible through consistent spacing, soft borders, and quiet color hierarchy.

## Colors

The palette is built from neutral grays and a single green brand/action family.

- Primary green is the brand and action color. Use it for active navigation, primary buttons, selected states, focus borders, success dots, progress fills, and high-confidence workflow states.
- Neutral grays carry most of the interface. Backgrounds are pale gray, panels are white, controls are light gray, and text ranges from near-black headings to muted metadata.
- Red, amber, and blue are semantic only. Red indicates destructive, lost, failed, or overdue states. Amber indicates warning or pending attention. Blue is informational and should be rare.
- Avoid large green surfaces. Most screens should read as white and gray with precise green accents.

## Typography

The UI uses a system sans stack led by Inter. Type is intentionally small: 9px to 10px is the default operating range, 11px to 12px is reserved for local titles. This creates the data-dense feel of an internal tool.

Use semibold weight for table identifiers, labels, active navigation, compact headings, and primary values. Avoid large hero typography. Line height should stay tight but readable. Letter spacing stays at zero.

## Layout & Spacing

Pages use a fixed top navigation bar and a scrollable main area on a pale gray background. Content is centered in a wide container that can stretch to 1400px or 1600px for operational tables.

Common layout patterns:

- A breadcrumb or local nav panel at the top of each workflow.
- Filter panels above tables, usually in a single dense row on desktop.
- White rounded panels for forms, tables, receipts, cards, and KPI groups.
- Tables with compact 8px vertical and 12px horizontal cell padding.
- Right-side drawers for document details and inline workflow updates.
- Modals for creation, import, export, and batch actions.

Spacing should be regular and compact. Prefer 8px, 12px, and 16px gaps. Use 32px as page padding, not as internal component spacing.

## Elevation & Depth

Depth is subtle. Most panels use a thin border and a small shadow. Dropdowns, modals, toasts, and drawers use stronger shadows because they float above tables and dense content.

Do not create dramatic layered compositions. Elevation is functional: it separates menus, overlays, toasts, and drawers from the working surface.

## Shapes

The design uses rounded rectangles heavily, but with restraint:

- Primary panels and large cards use 16px corners.
- Inputs and select-like controls use 12px corners.
- Buttons use 8px corners.
- Badges and small status dots are fully rounded.
- Avatars in this product are square, not circular.

The overall shape language is soft but not playful.

## Components

Navigation is a fixed white translucent bar with small text links. The active link is semibold green. User account controls are compact and bordered.

Filter controls are light-gray fields inside white panels. Inputs usually have no heavy focus ring; the preferred focus treatment is a green border. Selects and searchable dropdowns should feel like compact form controls, not large menu widgets.

Tables are the dominant information surface. Header rows use light gray backgrounds and muted uppercase or semibold labels. Body rows use thin separators and very subtle hover states. Primary identifiers such as document codes and package codes should be semibold dark text.

Buttons are compact. Primary actions are green with white text. Secondary actions are white with gray borders. Destructive actions keep a white background with red text and red border unless the action must be highly prominent.

Badges are small pills. They may use configured status colors, but they should retain dark readable text and compact padding.

Toasts appear in the top-right below the nav. They are white, bordered, softly shadowed, and include a small colored dot to indicate success, warning, error, or info.

Drawers are used for detail and action workflows without leaving the table. Drawer forms should keep the same compact inputs, small labels, and subtle section dividers.

## Do's and Don'ts

Do:

- Keep screens dense, structured, and optimized for repeated operational use.
- Use F88 green for important actions and active states.
- Use white panels on the pale gray workspace.
- Keep table text compact and scannable.
- Use thin borders and soft shadows to separate surfaces.
- Use semantic colors only when they add operational meaning.
- Prefer direct labels, status names, dates, codes, and counts over explanatory copy.

Don't:

- Do not create marketing-style hero sections.
- Do not introduce large illustrations, decorative gradients, or oversized cards.
- Do not make the UI dominated by green.
- Do not use large typography inside operational panels.
- Do not add heavy shadows, glass effects, or dramatic depth.
- Do not use rounded, decorative badges for ordinary text when a simple label is enough.
- Do not hide dense table workflows behind sparse card layouts unless the workflow is explicitly card-based.
