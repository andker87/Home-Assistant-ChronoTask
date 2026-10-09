# ChronoTask

**Advanced weekly scheduling for Home Assistant**

ChronoTask is a Home Assistant integration that lets you create, visualize and manage **recurring weekly schedules** through a clear, editable and truly usable visual planner.

<img width="784" height="563" alt="ChronoTask_1" src="https://github.com/user-attachments/assets/561024b8-fb1b-431c-928f-f957454f1b9c" />


## 📖 Contents

- [Was this really necessary?](#-was-this-really-necessary--yes)
- [Why ChronoTask](#-why-chronotask)
- [The honest story behind the project](#-the-honest-story-behind-the-project)
- [Features](#-features)
- [Project components](#-project-components)
- [Installation](#-installation)
- [Contributing](#-contributing)

---

## ❓ Was this really necessary? ✅ Yes.

Over the past months, tado° [announced](https://community.home-assistant.io/t/tado-rate-limiting-api-calls/928751) significant limitations to the usage of its cloud APIs, introducing very restrictive daily quotas for users without a paid subscription.

One thing needs to be made clear right away: the official tado° integration for Home Assistant still works.
This project does **not** exist because “tado stopped working”.

The real problem is **where the logic lives**.

I could have kept using the tado° planner, but that would have meant:

- relying on an external cloud service for a critical part of my home automation
- being subject to usage limits introduced after the hardware was purchased
- risking to suddenly lose functionality when the daily API rate limit is reached

In my setup, the planner was not only used to schedule heating. It was also used to:
- restore radiator valves to “auto” mode (scheduled operation)
- after window open/close events
- or after temporary manual overrides

In other words, part of my **automation logic** was running outside my home.

Delegating such a central piece of logic to an external service —with the concrete risk of being locked out due to an arbitrarily imposed limit— **was not a sustainable option**.

That is why I decided to bring the **scheduling logic back home**.

---

## 🔍 Why ChronoTask

I looked for alternatives.

There are valid scheduling components in Home Assistant, but **none of them provided a clear and intuitive weekly visual representation** comparable to the tado° planner.

The problem was not “how to schedule things”, but **how to see, understand and manage a whole week at a glance**.

ChronoTask was born from this gap, more from a **missing user experience** than from a technical limitation.

---

## 🧠 The honest story behind the project

I do not have a software development background.

When I decided to try building ChronoTask, I immediately hit a wall: **I did not know how to do it**.

Fortunately (or unfortunately? 🤔), we live in the age of **AI**.

With **a lot of patience**, **many hours of testing**, trial and error, and continuous iteration, I gradually guided AI tools toward the development of this component.

👉 **ChronoTask is developed 100% with the help of AI.**

This also means that:
- some parts of the code may look “unusual”
- not every solution is perfectly idiomatic or elegant

For this reason:
- **everyone is invited to read and review the code**
- pull requests, suggestions and improvements are more than welcome
- issues and feature requests will be evaluated — often together with AI 🙂

ChronoTask is an **open**, **honest** and **evolving** project.

---

## 🚀 Features

ChronoTask provides:

- 📅 **Weekly planner** with configurable time slots
- 🧩 **Recurring rules** with optional start / end
- 🗓 **Multi-slot rules** — one rule, one action, covering multiple days/times at once
- 🌙 **Overnight and multi-day slots** — e.g. Monday 22:00 → 06:00, or Monday 09:00 → Thursday 09:00, drawn across every day they cover
- 🔎 **Searchable entity picker** — find an entity by name or id, with icon and friendly name
- 🎨 **Colors and icons** for quick visual recognition
- 🏷 **Tags** to organize and manage groups of rules
- ✅ **Single or bulk enable / disable**
- 🔄 **Real-time UI updates** (always in sync with state)
- 🖥 **Weekly Card** with calendar-style layout
- 🗂 **Tag Manager Card** for bulk operations
- 📱 **Mobile-friendly UI** (scrolling, adaptive layout, readable)
- 🌍 **Multi-language UI** — Italian, English, French, German, Spanish, Chinese (auto-detected from Home Assistant, English fallback)


![ChronoTask_2](https://github.com/user-attachments/assets/0f7e469a-06fe-4eff-8d6b-91bcf57c0a5f)

![ChronoTask_3](https://github.com/user-attachments/assets/f8aac1e5-ba6e-4bea-be85-9b82e7408733)

![ChronoTask_4](https://github.com/user-attachments/assets/25d5f971-a89a-47c1-8dde-73f37c371c02)


---

## 🧩 Project components

ChronoTask is not just a card, but a small ecosystem:

### 🔧 Backend integration
- Centralized management of planners and rules
- Services to create, update and remove rules
- Single source of truth for scheduling state

### 📅 Weekly Card
- Weekly calendar-style visualization (slots crossing midnight or spanning several days continue in the next day's column)
- Rule creation and editing directly from the UI, with a searchable entity picker
- Fully usable on desktop and mobile

### 🏷 Tag Manager Card
- Bulk rule management via tags
- Enable / disable entire groups with one click

---

## 📦 Installation

### ✅ Installation via HACS (recommended)

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=andker87&repository=Home-Assistant-ChronoTask&category=integration)

ChronoTask is available in the **HACS default store**.

1. Open **HACS**
2. Go to **Integrations**
3. Search for **ChronoTask**
4. Click **Download**
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → Add integration**
7. Search for **ChronoTask**

#### 📌 Frontend cards (automatic)
ChronoTask includes two custom Lovelace cards. The integration registers them **automatically** (with the version in the URL, so an update is never masked by a browser or CDN cache such as Cloudflare): there is nothing to add under Resources.

After the restart, the cards appear in the Custom card section when adding a new card to a dashboard.

> If you previously added `/local/chronotask/...` under **Settings → Dashboards → ⋮ → Resources**, you can safely remove those two entries.

#### 🌙 Overnight and multi-day rules
No extra setting is needed for a slot that crosses midnight: if the end time is earlier than the start time (e.g. Monday 22:00 → 06:00) and *End day* is left on “Same as start”, the end action runs the **next day**. For slots longer than that (e.g. Monday 09:00 → Thursday 09:00) choose the *End day* explicitly.

---
### 🛠️ Manual Installation

If you prefer not to use HACS, you can install the integration manually:

1. Download the latest release from this repository
2. Extract the archive
3. Copy the folder custom_components/chronotask into:
```
<config>/custom_components/chronotask
```
4. Restart Home Assistant  
5. Go to Settings → Devices & Services → Add Integration  
6. Search for ChronoTask
The integration will automatically copy the required frontend files into:
```
<config>/www/chronotask/
```
The cards are then registered automatically, both with storage-mode and YAML-mode dashboards.

---
### ℹ️ Notes
- After an update, restart Home Assistant and refresh the browser once
- On mobile apps, if you notice UI issues, try fully closing and reopening the app
- The integration is actively evolving; some parts may change over time

---

## 🔮 Next steps

ChronoTask is a work in progress, actively developed based on real-world usage and community feedback.

### Coming soon

- 🔲 Lane layout in the weekly planner — overlapping rules shown side by side instead of stacking

### On the roadmap

- 📅 Rule validity period — valid_from / valid_until to define seasonal or temporary rules (e.g. summer mode, school schedule)
- ⚡ Execution conditions — run a rule only if a specific HA entity is in a given state
- 🔁 Non-weekly recurrence — support for "every N days" or "first Monday of the month"
- 📆 One-off exceptions — skip or force a rule on a specific date without modifying the base rule
  
### Longer term

- 📊 Daily / compact view — agenda-style card, useful on mobile dashboards
- 🔀 Drag & drop rescheduling — move a block directly from the planner card
- 💾 Export / import rules — backup, restore, and share configurations between HA instances
- 🔔 Trigger notifications — optional HA notification on every rule execution
- 🔌 Switch entity per rule — expose each rule as a switch.* entity, usable in standard automations
  
---

## 🤝 Contributing

ChronoTask was born from a real need and grows through collaboration.

- Report bugs and issues via **GitHub Issues**
- Propose ideas and improvements
- Open a **Pull Request** if you want to contribute

ChronoTask does not aim to replace anything.  
It simply aims to make **weekly scheduling in Home Assistant readable, manageable and fully local**.
