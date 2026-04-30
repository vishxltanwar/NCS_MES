# Napino MES - AI Agent Context Document

This document is designed to provide comprehensive context about the **Napino MES (Manufacturing Execution System)** project to any AI agent joining the development process. 

## Project Overview
Napino MES is a production tracking and serial number generation system built specifically for a manufacturing floor (Napino Control Systems - Halol). The system acts as a dashboard for machine operators and managers to track production metrics, generate laser marking serial numbers, and review historical shifts.

## Tech Stack
*   **Backend Framework:** Django (recently migrated from FastAPI).
*   **API Framework:** Django REST Framework (DRF) using `@api_view` decorators for lightweight functional views.
*   **Database:** PostgreSQL.
*   **Frontend:** Vanilla HTML, Vanilla JavaScript, and TailwindCSS (via CDN). No frontend frameworks (like React or Vue) are used. 
*   **Frontend Libraries:** Google Material Symbols (icons), Google Fonts (Inter, Space Grotesk, JetBrains Mono).

## Core Functionality & Features
1.  **Serial Number Generation (`/api/generate`)**
    *   **Format:** `PPPPP` (Part Number) + `LL` (Line No) + `S` (Shift) + `YYDDD` (Year/Julian Day) + `NNN` (3-digit daily sequence).
    *   **Integration:** Once a serial is generated, it writes the string to a network shared drive text file (`\\172.16.61.202\Common Folder\Machine Data\LaserData\serial.txt`) where a physical Laser Marking Machine reads it and marks the physical component.
2.  **Part Management (`/add-part`)**
    *   Registers new parts into the system. Validates part types against fixed categories (Rotor, Stator, Motor).
3.  **Real-Time Dashboards (`/dashboard`, `/laser-marking`, `/machine-overview`)**
    *   The frontend uses `setInterval` paired with JavaScript `fetch()` calls to ping DRF API endpoints (e.g., `/api/stats`, `/api/serials`) to implement real-time UI updates without WebSockets.
4.  **Reporting & Traceability (`/shift-report`, `/production-log`, `/traceability`)**
    *   Provides aggregated statistics on production performance across standard shifts.
    *   **Shifts:** A (Morning 06:30-15:00), B (Afternoon 15:00-23:30), C (Night 23:30-06:30), G (General 08:30-17:00).
5.  **Authentication (`/api/login`, `login.html`)**
    *   Standard Django session cookie authentication. 

## Project Structure
*   `mes_project/`: The main Django settings and root URL configuration directory.
*   `core/`: The primary Django app containing the business logic.
    *   `models.py`: Contains the `Serial` and `Part` database models.
    *   `views.py`: Contains *both* standard Django template rendering views (for the pages) and DRF `@api_view` endpoints (for the JS `fetch` calls).
    *   `urls.py`: Maps routes to either template views or API endpoints.
    *   `templates/`: Contains all HTML files (e.g., `base.html` for layout, `dashboard.html`, `add_part.html`, etc.).
*   `stitch_screen.html`: A standalone promotional or alternative login screen with high-end generative UI styling.

## Design & UI Aesthetics
*   The application prioritizes a **"premium, modern, and high-tech"** aesthetic.
*   It extensively uses glassmorphism (`backdrop-blur`), mesh gradients, subtle CSS pulse/bounce animations, and customized scrollbars to feel like advanced industrial software. 
*   **Strict Rule:** No bare minimum MVPs. All new UI components must match this premium styling with proper padding, shadows, hover states, and smooth transitions.

## Critical Development Rules for AI Agents
1.  **Vanilla JS Strictness:** Do not introduce frontend frameworks or build steps (Webpack/Vite/Babel). Write vanilla JavaScript. When rendering HTML from JS (e.g., inside `.map().join('')`), rely on string concatenation.
2.  **Timezones:** The plant operates in Indian Standard Time (IST, UTC+05:30). The backend API endpoints must return timestamps in **ISO 8601 format with the explicit `+05:30` timezone offset** attached (e.g., `s.created_at.astimezone(IST).isoformat()`). The frontend `Date` object will natively parse this and use `.toLocaleString()` to avoid double-timezone-offset bugs.
3.  **Styling constraints:** All styling relies on TailwindCSS utility classes directly in the HTML template files. Avoid writing raw `<style>` blocks unless absolutely necessary for complex keyframe animations or custom scrollbars.
