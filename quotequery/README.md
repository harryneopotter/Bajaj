# 🏷️ QuoteQuery: Bajaj Sports Analytics Assistant

QuoteQuery is a mobile-first, conversational analytics tool designed for the Bajaj Sports sales team and management. It provides instant insights from ~10 years of historical quote data (over 1,900 quotes and ₹99+ Crore in value) via a simple chat-like interface.

## 🛠️ Tech Stack

**1. Frontend (Client-Side)**
* **Vanilla HTML5 / CSS3 / JavaScript:** Zero build steps or heavy frameworks (like React/Vue) to ensure instant load times on mobile networks.
* **PWA Ready:** Designed to function like a native iOS/Android app.
* **Modern CSS:** Uses native CSS variables (`:root`), Flexbox, and CSS Grid for responsive, card-based mobile layouts.
* **Async Fetch API:** Handles backend communication without page reloads.

**2. Backend (Server-Side)**
* **Language:** Python 3
* **Framework:** **FastAPI** for extreme speed, asynchronous capabilities (`async def`), and native JSON handling.
* **Server:** Uvicorn (ASGI web server) running on port `8082`.

**3. Database & Data Pipeline**
* **Database:** **SQLite3** (`quotes.db`). Shared with the QuoteGen app for zero-configuration, single-file portability.
* **Data Origin:** Historical data extracted from thousands of unstructured Word documents via a custom Python `docx` heuristic pipeline.

**4. Query Engine / AI Logic**
* **Current Routing:** Python Regular Expressions (`re`) and string matching heuristics for instant, deterministic SQL queries.
* **Planned AI Integration:** **Gemma 4-31B** (via Google AI Studio) acting strictly as an *Intent Resolver* to translate complex natural language into structured SQL parameters.

**5. Infrastructure & Deployment**
* **Host Environment:** Ubuntu Linux VM.
* **Public Access:** **Cloudflare Tunnels** (`cloudflared`) securely exposes the app to `https://ask.bajajsports.com`.

---

## 💻 Running Locally for Development

### Prerequisites
* Python 3.8+
* Ensure the SQLite database exists at `../quotegen/quotes.db` (relative to the configured data directory).

### Setup & Run
1. **Navigate to the QuoteQuery directory:**
   ```bash
   cd /home/sachin/work/bajaj/quotequery
   ```

2. **Install dependencies:**
   ```bash
   pip install fastapi uvicorn python-dotenv
   ```

3. **Start the server:**
   *For hot-reloading during development:*
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8082 --reload
   ```
   *Or using the built-in runner:*
   ```bash
   python3 main.py
   ```

4. **Access the App:**
   Open your browser and navigate to `http://localhost:8082`.

### Environment Variables
Create a `.env` file in the `quotequery` directory for LLM features:
```env
AI_STUDIO_KEY=your_google_ai_studio_api_key
```

---

## 🎨 How to Modify the UI/UX

Because QuoteQuery uses vanilla web technologies, modifying the UI is incredibly straightforward—there is no `npm build` or Webpack compilation required.

### Directory Structure
* `static/index.html` - The entire frontend (HTML structure, CSS styles, and JS logic).
* `main.py` - The FastAPI backend routing and API endpoints.

### Changing Styles (CSS)
Open `static/index.html` and look for the `<style>` block at the top. 
* Change the primary color scheme by modifying the CSS variables: `:root { --primary: #1a237e; --bg: #f8f9fa; }`
* Adjust button sizes, padding, and layout directly in the `.big-btn` or `.answer-card` classes.

### Adding a New Quick-Action Button
1. **Frontend (`static/index.html`):**
   Add a new button inside the `<div class="button-grid">`. Use the `ask()` function to send a specific query string to the backend.
   ```html
   <div class="big-btn" onclick="ask('Show me the latest products')">
       <span>🆕</span> New Products
   </div>
   ```

2. **Backend (`main.py`):**
   Open `main.py`, locate the `query()` endpoint, and add a string-matching routing block to intercept your new query string before it hits the LLM fallback.
   ```python
   if "latest products" in text:
       # Fetch data from DB
       # Format response with HTML tags (e.g., <br> and <b>)
       return {"answer": "Your custom formatted response here"}
   ```

3. **Refresh your browser!** Changes to `index.html` show up immediately upon page refresh. Changes to `main.py` will hot-reload automatically if running with `uvicorn --reload`.