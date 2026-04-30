# Napino MES

Napino MES is a production tracking and serial number generation system built specifically for a manufacturing floor (Napino Control Systems - Halol). The system acts as a dashboard for machine operators and managers to track production metrics, generate laser marking serial numbers, and review historical shifts.

## Tech Stack
*   **Backend Framework:** Django 
*   **API Framework:** Django REST Framework (DRF) 
*   **Database:** PostgreSQL
*   **Frontend:** Vanilla HTML, Vanilla JavaScript, and TailwindCSS (via CDN).

## Core Functionality & Features
1.  **Serial Number Generation (`/api/generate`)**
    *   **Format:** `PPPPP` (Part Number) + `LL` (Line No) + `S` (Shift) + `YYDDD` (Year/Julian Day) + `NNN` (3-digit daily sequence).
    *   **Integration:** Once a serial is generated, it writes the string to a network shared drive text file where a physical Laser Marking Machine reads it and marks the physical component.
2.  **Part Management (`/add-part`)**
    *   Registers new parts into the system. Validates part types against fixed categories (Rotor, Stator, Motor).
3.  **Real-Time Dashboards (`/dashboard`, `/laser-marking`, `/machine-overview`)**
    *   Real-time UI updates via API polling.
4.  **Reporting & Traceability (`/shift-report`, `/production-log`, `/traceability`)**
    *   Aggregated statistics on production performance across standard shifts (A, B, C, G).

## How to Run

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd napino_mes
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```powershell
   pip install -r requirements.txt
   ```

4. **Environment Variables:**
   Copy `.env.example` to `.env` and fill in your database details.
   ```powershell
   cp .env.example .env
   ```

5. **Run Database Migrations:**
   Make sure you have PostgreSQL running and the database created as defined in your `.env`.
   ```powershell
   python manage.py migrate
   ```

6. **Start the Server:**
   ```powershell
   python manage.py runserver
   ```

Once started, open your web browser and navigate to: [http://127.0.0.1:8000](http://127.0.0.1:8000)
