# How to Run Napino MES

Follow these steps in your Windows PowerShell terminal to start the Napino MES application.

## 1. Open Terminal and Navigate to Project
Open your PowerShell terminal and change directory to the project folder:
```powershell
cd c:\Users\vishalt\Documents\napino_mes
```

## 2. Activate Virtual Environment
Activate the Python virtual environment to use the isolated dependencies:
```powershell
.\venv\Scripts\activate
```
> [!NOTE]
> Once activated, you will see `(venv)` appear at the beginning of your PowerShell prompt.

> [!TIP]
> If you get an error that "cannot be loaded because running scripts is disabled on this system", run this command once to fix it: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

## 3. Install Requirements (If needed)
If this is your first time or dependencies have changed, install them with:
```powershell
pip install -r requirements.txt
```

## 4. Run Database Migrations
Make sure your PostgreSQL database schema is fully updated:
```powershell
python manage.py migrate
```

## 5. Start the Server
Finally, run the Django development server:
```powershell
python manage.py runserver
```

> [!IMPORTANT]
> Keep this terminal window open! Closing it will stop the server.

Once you see the message `Starting development server at http://127.0.0.1:8000/`, open your web browser and navigate to:
[http://127.0.0.1:8000](http://127.0.0.1:8000)
