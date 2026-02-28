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
- [Intallation](#-installation)
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
- 🎨 **Colors and icons** for quick visual recognition
- 🏷 **Tags** to organize and manage groups of rules
- ✅ **Single or bulk enable / disable**
- 🔄 **Real-time UI updates** (always in sync with state)
- 🖥 **Weekly Card** with calendar-style layout
- 🗂 **Tag Manager Card** for bulk operations
- 📱 **Mobile-friendly UI** (scrolling, adaptive layout, readable)


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
- Weekly calendar-style visualization
- Rule creation and editing directly from the UI
- Fully usable on desktop and mobile

### 🏷 Tag Manager Card
- Bulk rule management via tags
- Enable / disable entire groups with one click

---

## 📦 Installation

### ✅ Installation via HACS (recommended)

1. Open **HACS**
2. Add this repository as a **Custom Integration**
3. Install **ChronoTask**
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add integration**
6. Search for **ChronoTask**

✅ The integration automatically installs and updates the required frontend files. The two ChronoTask Lovelace cards will appear in the **“Custom card”** section when adding a new card to a dashboard.

---
🛠️ Manual Installation

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
and serve them under:
```
/local/chronotask/
```
No manual Lovelace resource configuration is required.
<br>
---
### ⚠️ Lovelace YAML mode note

If you are using Lovelace in **YAML mode**, resources must be added manually:

```yaml
lovelace:
  resources:
    - url: /chronotask/chronotask-weekly.js
      type: module
    - url: /chronotask/chronotask-tag-manager.js
      type: module
```

---
### ℹ️ Notes
- After an update, a **browser refresh** may be required
- On mobile apps, if you notice UI issues, try fully closing and reopening the app
- The integration is actively evolving; some parts may change over time

---

## 🔮 Next steps

ChronoTask is a work in progress.  
Some possible future directions include:

- 📦 Native HACS integration (coming soon!)
- ⏱ Improved handling of **rules spanning across multiple days**  
  (for example overnight schedules)
- 📊 A **daily or compact view**, complementary to the weekly planner
- 🌍 **Multi-language support**
- 🧠 Further **mobile UX improvements**

Priorities will be driven by **real-world usage** and **community feedback**.

---

## 🤝 Contributing

ChronoTask was born from a real need and grows through collaboration.

- Report bugs and issues via **GitHub Issues**
- Propose ideas and improvements
- Open a **Pull Request** if you want to contribute

ChronoTask does not aim to replace anything.  
It simply aims to make **weekly scheduling in Home Assistant readable, manageable and fully local**.
