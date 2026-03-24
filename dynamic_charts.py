"""
Dynamic Report Generation System
- Converts natural language requests to SQL queries
- Generates matplotlib visualizations on-the-fly with chart type selection
- Intelligent chart type validation and auto-suggestions
- Integrates with chat interface for user-controlled visualization
"""

import os
import io
import json
import base64
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime
from groq import Groq
from database import db
from sqlalchemy import text as sa_text
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

DB_SCHEMA = """
CREATE TABLE flowers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL,
    price FLOAT NOT NULL
);

CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(80) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    phone VARCHAR(20) NOT NULL
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    flower_id INTEGER REFERENCES flowers(id),
    quantity INTEGER NOT NULL,
    total_price FLOAT NOT NULL,
    order_date TIMESTAMP DEFAULT NOW(),
    status VARCHAR(20) DEFAULT 'completed'
);
"""

COLORS = {
    'bg': '#0D1117',
    'text': '#E6EDF3',
    'muted': '#7D8590',
    'green': '#3FB950',
    'red': '#F85149',
    'blue': '#58A6FF',
    'yellow': '#D29922',
    'cyan': '#39C5CF'
}


def validate_sql_syntax(sql: str) -> bool:
    """
    Validate SQL query for safety and correctness.
    - Must start with SELECT
    - No dangerous keywords (INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER)
    - Basic GROUP BY validation
    """
    dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE', 'ALTER', 'CREATE']
    sql_upper = sql.strip().upper()
    
    if not sql_upper.startswith('SELECT'):
        return False
    
    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            return False
    
    return True


def detect_missing_group_by_columns(sql: str) -> list:
    """
    Detect potential GROUP BY errors where selected columns aren't in GROUP BY.
    Returns list of potential issues, or empty list if OK.
    """
    warnings = []
    sql_upper = sql.upper()
    
    if 'GROUP BY' not in sql_upper or 'SELECT' not in sql_upper:
        return warnings
    
    # Extract SELECT and GROUP BY parts
    try:
        select_part = sql_upper[sql_upper.find('SELECT'):sql_upper.find('FROM')]
        group_part = sql_upper[sql_upper.find('GROUP BY'):]
        
        # Check for common GROUP BY issues
        if 'DATE(' in select_part and 'GROUP BY DATE(' not in group_part:
            warnings.append("DATE() function in SELECT but not in GROUP BY - may cause error")
        
        if 'DATE(O.ORDER_DATE)' in select_part or 'O.ORDER_DATE::DATE' in select_part:
            if 'GROUP BY' in sql_upper and 'DATE(O.ORDER_DATE)' not in group_part and 'O.ORDER_DATE::DATE' not in group_part:
                warnings.append("ORDER_DATE in SELECT but missing from GROUP BY")
    except:
        pass
    
    return warnings


def detect_report_request(user_message: str) -> bool:
    """
    Detect if user is asking for a VISUALIZATION/CHART (not just data).
    
    WHY: The old keywords ('sales', 'show', 'display') appeared in regular 
    data queries too. Now we only match explicit visualization requests.
    
    Returns True only for chart/graph/visualization requests.
    """
    visualization_keywords = [
        'show chart', 'display chart', 'show graph', 'display graph',
        'create chart', 'create graph', 'generate chart', 'generate graph',
        'plot', 'visualize', 'visualization', 'visual report',
        'chart of', 'graph of', 'graph showing'
    ]
    message_lower = user_message.lower()
    return any(keyword in message_lower for keyword in visualization_keywords)


def extract_chart_type_from_input(user_input: str) -> str:
    """Extract chart type from user's natural language input."""
    chart_keywords = {
        'pie': ['pie', 'donut', 'distribution', 'proportion', 'breakdown'],
        'bar': ['bar', 'column', 'comparison', 'vs', 'compare'],
        'line': ['line', 'trend', 'over time', 'progression', 'timeline'],
        'scatter': ['scatter', 'correlation', 'relationship', 'xy'],
    }
    
    input_lower = user_input.lower()
    for chart_type, keywords in chart_keywords.items():
        if any(kw in input_lower for kw in keywords):
            return chart_type
    
    return None  # User didn't specify


def validate_chart_for_data(chart_type: str, columns: list, data: list) -> tuple:
    """Check if chart type is suitable for data."""
    
    if not data:
        return (False, 'bar', 'No data to visualize')
    
    num_columns = len([c for c in columns if isinstance(data[0].get(c), (int, float))])
    num_rows = len(data)
    
    if chart_type == 'line':
        if num_columns < 2:
            return (False, 'bar', 'Line chart needs 2+ numeric columns')
        return (True, chart_type, '✅ Perfect for trends!')
    
    elif chart_type == 'pie':
        if num_rows > 10:
            return (False, 'bar', f'❌ Too many items ({num_rows}). Try bar chart.')
        if num_columns < 1:
            return (False, 'bar', 'Pie needs numeric data')
        return (True, chart_type, '✅ Good for proportions!')
    
    elif chart_type == 'bar':
        if num_columns < 1:
            return (False, None, 'Bar chart needs numeric data')
        return (True, chart_type, '✅ Works for most data!')
    
    elif chart_type == 'scatter':
        if num_columns < 2:
            return (False, 'bar', 'Scatter needs X and Y values')
        return (True, chart_type, '✅ Good for relationships!')
    
    return (False, 'bar', 'Unknown chart type')


def suggest_best_chart(columns: list, data: list) -> str:
    """Auto-suggest best chart based on data structure."""
    
    if not data:
        return 'bar'
    
    num_columns = len([c for c in columns if isinstance(data[0].get(c), (int, float))])
    num_rows = len(data)
    
    if num_rows <= 8 and num_columns == 1:
        return 'pie'
    elif num_columns >= 2:
        return 'line'
    else:
        return 'bar'


def is_inventory_query(user_request: str) -> bool:
    """
    Detect if request is asking for INVENTORY/STOCK data (not sales/orders).
    
    INVENTORY queries should return ONLY: SELECT name, quantity FROM flowers;
    Do NOT use JOINs, GROUP BY, ORDER BY, or calculations with orders table.
    """
    inventory_keywords = [
        'stock', 'inventory', 'flowers in', 'how many', 'quantities',
        'what flowers', 'list flowers', 'all flowers', 'flower list',
        'available flowers', 'in stock'
    ]
    request_lower = user_request.lower()
    return any(keyword in request_lower for keyword in inventory_keywords)


def extract_month_year(user_request: str) -> tuple:
    """
    Extract month/year from user request with fuzzy matching.
    Returns: (month_number, year_number, month_name) or (None, None, None)
    
    Examples:
    - "sales of february" -> (2, 2026, 'February')
    - "sales fen" -> (2, 2026, 'February') [typo for Feb]
    - "report for march" -> (3, 2026, 'March')
    """
    import re
    from datetime import datetime
    from difflib import get_close_matches
    
    request_lower = user_request.lower()
    current_year = datetime.now().year
    
    months = {
        'january': (1, 'January'), 'february': (2, 'February'), 'march': (3, 'March'), 
        'april': (4, 'April'), 'may': (5, 'May'), 'june': (6, 'June'), 
        'july': (7, 'July'), 'august': (8, 'August'), 'september': (9, 'September'), 
        'october': (10, 'October'), 'november': (11, 'November'), 'december': (12, 'December'),
        'jan': (1, 'January'), 'feb': (2, 'February'), 'mar': (3, 'March'), 'apr': (4, 'April'), 
        'jun': (6, 'June'), 'jul': (7, 'July'), 'aug': (8, 'August'), 'sep': (9, 'September'), 
        'oct': (10, 'October'), 'nov': (11, 'November'), 'dec': (12, 'December'),
        # Common typos
        'fen': (2, 'February'), 'feb': (2, 'February'),
        'mach': (3, 'March'), 'marc': (3, 'March'),
        'apri': (4, 'April'),
        'sept': (9, 'September'),
    }
    
    for month_key, (num, name) in months.items():
        if month_key in request_lower:
            return num, current_year, name
    
    # Fuzzy match ONLY for short words (3-5 chars) that could be typos
    # Use high cutoff (0.75) to avoid false positives like "report" -> "sept"
    words = request_lower.split()
    avoid_fuzzy_match = {'that', 'this', 'from', 'with', 'have', 'been', 'will', 'can', 
                         'also', 'show', 'give', 'make', 'report', 'chart', 'graph', 'data',
                         'sales', 'order', 'stock'}
    
    for word in words:
        # Only try fuzzy match on 3-5 character words (typical typo length)
        if 3 <= len(word) <= 5 and word not in avoid_fuzzy_match:
            matches = get_close_matches(word, months.keys(), n=1, cutoff=0.75)
            if matches:
                month_key = matches[0]
                num, name = months[month_key]
                print(f"[MONTH] Fuzzy matched '{word}' to '{month_key}' (cutoff: 0.75)")
                return num, current_year, name
    
    # If no month found, return None
    return None, None, None


def generate_sql_for_report(user_request: str) -> str:
    """
    Use Groq LLM to convert natural language request to SQL query.
    
    Handles three main query types:
    - INVENTORY: Simple, no JOINs needed. Returns: SELECT name, quantity FROM flowers;
    - MONTH-BASED: Sales for specific month. Pass month info to LLM with instructions
    - SALES/ANALYTICS: Complex queries with JOINs and GROUP BY
    
    Args:
        user_request: Natural language description (e.g., "Show revenue by flower") 
    Returns:
        SQL query string
    """
    
    if is_inventory_query(user_request):
        print(f"[SQL] Detected INVENTORY query - returning direct SQL")
        return "SELECT name, quantity FROM flowers ORDER BY quantity DESC;"
    
    month_num, year_num, month_name = extract_month_year(user_request)
    
    # Check if user is asking for a "report" but didn't specify month
    request_lower = user_request.lower()
    if not month_num and any(word in request_lower for word in ['report', 'this report', 'that report']):
        print(f"[WARNING] User asked for '{user_request}' but no month was specified")
        print(f"[HINT] Please specify which month (e.g., 'February report', 'March report')")
        raise ValueError(
            f"Please specify which month you want the report for. "
            f"For example: 'line graph for February' or 'March sales report'. "
            f"Available months: January, February, March, April, May, June, July, August, September, October, November, December"
        )
    
    month_context = ""
    if month_num:
        print(f"[SQL] Detected MONTH query: {month_name} {year_num}")
        month_context = f"""
MONTH FILTER REQUIREMENT:
The user is asking for data for {month_name} {year_num}.
Use PostgreSQL date extraction to filter: WHERE EXTRACT(MONTH FROM o.order_date) = {month_num} AND EXTRACT(YEAR FROM o.order_date) = {year_num}
"""
    
    prompt = f"""You are a PostgreSQL expert for a flower shop database.

Database Schema:
{DB_SCHEMA}

User Request: "{user_request}"{month_context}

Generate a SELECT query that fulfills this request.

CRITICAL RULES - ABSOLUTELY NO EXCEPTIONS:

1️⃣ FORBIDDEN PATTERNS - NEVER generate these:
   ❌ For inventory: DO NOT JOIN with orders table
   ❌ DO NOT use: GROUP BY f.name (invalid - causes SQL errors)
   ❌ WRONG: SELECT f.name, ROUND(SUM(o.quantity)::numeric * f.price::numeric, 2) AS sales, GROUP BY f.name
   ❌ WRONG: Using f.price in SELECT without aggregating it in GROUP BY
   ❌ If using GROUP BY, complete syntax: GROUP BY f.id, f.name (include ALL non-agg columns)
   ❌ DO NOT add date filters (WHERE o.order_date...) UNLESS the user explicitly asks for "recent", "last week", "last month", "today", etc.

2️⃣ SAFE PATTERNS - Use these:
   ✅ For sales queries: GROUP BY f.id, f.name (not just f.name)
   ✅ For customer queries: GROUP BY c.id, c.name
   ✅ For calculations: ROUND(SUM(o.total_price)::numeric, 2)
   ✅ When multiplying: ROUND(SUM(o.quantity)::numeric * AVG(f.price)::numeric, 2)
   ✅ For month/year filtering: EXTRACT(MONTH FROM o.order_date) = month_num AND EXTRACT(YEAR FROM o.order_date) = year_num

3️⃣ RETURN FORMAT:
   - Return ONLY the raw SQL query - no explanation, markdown, or code blocks
   - Use proper JOINs (INNER JOIN / LEFT JOIN as needed)
   - Limit results to 100 rows max LIMIT 100
   - Ensure column names are descriptive for visualization

4️⃣ DATE FILTERING:
   - "last week": WHERE o.order_date >= CURRENT_DATE - INTERVAL '7 days'
   - "last month": WHERE o.order_date >= CURRENT_DATE - INTERVAL '30 days'
   - "today": WHERE DATE(o.order_date) = CURRENT_DATE
   - Use DATE comparison, NOT LOWER() on dates

5️⃣ CAST RULES (PostgreSQL):
   - ALWAYS: ::numeric cast before ROUND()
   - WRONG: ROUND(SUM(o.quantity) * f.price, 2)
   - CORRECT: ROUND(SUM(o.quantity)::numeric * AVG(f.price)::numeric, 2)

6️⃣ FOR TIME-SERIES / LINE CHARTS (CRITICAL):
   - Group by DATE: GROUP BY DATE(o.order_date) - MUST include date in GROUP BY!
   - If also including flower names: GROUP BY DATE(o.order_date), f.id, f.name
   - Results should have ONE ROW PER DATE for trends
   - Don't return individual orders - always aggregate by date for time-based queries
   - **CRITICAL**: When you SELECT DATE(...), you MUST include DATE(...) in GROUP BY clause
   - ORDER BY DATE to ensure chronological order

PROVEN EXAMPLES:
- Request: "Show revenue by flower"
  Response: SELECT f.id, f.name AS flower, ROUND(SUM(o.total_price)::numeric, 2) AS revenue FROM orders o JOIN flowers f ON o.flower_id = f.id GROUP BY f.id, f.name ORDER BY revenue DESC;

- Request: "Top customers by spending"
  Response: SELECT c.id AS customer_id, c.name, COUNT(o.id) AS orders, ROUND(SUM(o.total_price)::numeric, 2) AS total_spent FROM customers c LEFT JOIN orders o ON c.id = o.customer_id GROUP BY c.id, c.name ORDER BY total_spent DESC LIMIT 5;

- Request: "Sales last week" or "Line chart of sales"
  Response: SELECT DATE(o.order_date) AS order_date, SUM(o.quantity) AS quantity_sold, ROUND(SUM(o.total_price)::numeric, 2) AS daily_revenue FROM orders o WHERE o.order_date >= CURRENT_DATE - INTERVAL '7 days' GROUP BY DATE(o.order_date) ORDER BY order_date;

- Request: "February sales by flower"  
  Response: SELECT DATE(o.order_date) AS order_date, f.name AS flower_name, SUM(o.quantity) AS quantity_sold, ROUND(SUM(o.total_price)::numeric, 2) AS total_revenue FROM orders o JOIN flowers f ON o.flower_id = f.id WHERE EXTRACT(MONTH FROM o.order_date) = 2 AND EXTRACT(YEAR FROM o.order_date) = 2026 GROUP BY DATE(o.order_date), f.id, f.name ORDER BY order_date DESC;

- Request: "Daily sales for February"
  Response: SELECT DATE(o.order_date) AS order_date, SUM(o.quantity) AS qty_sold, ROUND(SUM(o.total_price)::numeric, 2) AS daily_total FROM orders o WHERE EXTRACT(MONTH FROM o.order_date) = 2 AND EXTRACT(YEAR FROM o.order_date) = 2026 GROUP BY DATE(o.order_date) ORDER BY order_date;

7️⃣ FOR SCATTER PLOTS (CRITICAL - 2 numeric columns):
   - Select TWO numeric columns - one for X-axis, one for Y-axis
   - Include all non-aggregate columns in GROUP BY (including IDs and names)
   - DO NOT use ORDER BY on columns not in SELECT/GROUP BY
   - If selecting f.price, must include it in GROUP BY: GROUP BY f.id, f.name, f.price
   - NEVER use ORDER BY with date/columns not aggregated

SCATTER PLOT EXAMPLES:
- Request: "Scatter plot of flower price vs sales"
  Response: SELECT f.id, f.name AS flower_name, f.price, SUM(o.quantity) AS quantity_sold FROM orders o JOIN flowers f ON o.flower_id = f.id GROUP BY f.id, f.name, f.price ORDER BY f.price;

- Request: "Scatter showing quantity vs total price"
  Response: SELECT o.id, o.quantity, o.total_price FROM orders o ORDER BY o.quantity;

- Request: "Scatter plot of order count vs average spending"
  Response: SELECT c.id, c.name, COUNT(o.id) AS order_count, ROUND(AVG(o.total_price)::numeric, 2) AS avg_spending FROM customers c LEFT JOIN orders o ON c.id = o.customer_id GROUP BY c.id, c.name ORDER BY order_count;
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}]
    )
    
    sql = response.choices[0].message.content.strip()
    sql = sql.replace("```sql", "").replace("```", "").strip()
    
    print(f"[LLM SQL GENERATED] {sql}")
    
    if not validate_sql_syntax(sql):
        raise ValueError("Generated SQL failed safety validation")
    
    warnings = detect_missing_group_by_columns(sql)
    if warnings:
        print(f"[SQL WARNINGS]:")
        for w in warnings:
            print(f"  ⚠️  {w}")
    
    return sql


def execute_sql(sql: str) -> tuple:
    """
    Execute SQL query safely with validation.
    
    Returns:
        Tuple of (data_list, column_names, error_message)
    """
    try:
        if not validate_sql_syntax(sql):
            return None, None, "SQL validation failed: Only SELECT queries allowed."
        
        result = db.session.execute(sa_text(sql))
        rows = result.fetchall()
        columns = list(result.keys())
        
        if len(rows) > 1000:
            rows = rows[:1000]
        
        data = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            for key, value in row_dict.items():
                if hasattr(value, '__class__') and 'Decimal' in str(value.__class__):
                    row_dict[key] = float(value)
                elif isinstance(value, (int, float)):
                    row_dict[key] = float(value) if isinstance(value, int) else value
            data.append(row_dict)
        
        if not data:
            return None, None, "Query returned no data."
        
        return data, columns, None
        
    except Exception as e:
        db.session.rollback()
        return None, None, f"SQL Error: {str(e)}"


def aggregate_data_for_chart(data: list, columns: list, chart_type: str) -> tuple:
    """
    Intelligently aggregate raw data when needed for specific chart types.
    
    For line charts: Try to group by date/time first, then by name
    For pie/bar: Group by label column, sum values
    
    Returns: (aggregated_data, updated_columns) where updated_columns reflects actual data
    """
    if not data or len(data) < 2:
        return data, columns
    
    if len(columns) < 2:
        return data, columns
    
    if chart_type in ('line', 'scatter') and len(data) > 8:
        print(f"[AGG] Line/scatter chart with {len(data)} rows - attempting aggregation")
        
        from collections import defaultdict
        import datetime
        
        date_col = None
        name_col = None
        id_col = None
        value_cols = []
        
        for col in columns:
            sample = data[0].get(col)
            if isinstance(sample, datetime.date) or isinstance(sample, datetime.datetime) or 'date' in col.lower():
                date_col = col
            elif isinstance(sample, str) and 'name' in col.lower():
                name_col = col
            elif 'id' in col.lower():  
                id_col = col
            elif isinstance(sample, (int, float)):
                value_cols.append(col)
        
        if date_col and value_cols:
            print(f"[AGG] Grouping by date column: {date_col}")
            by_date = defaultdict(lambda: {col: 0 for col in value_cols})
            
            for row in data:
                date_key = str(row[date_col])
                for val_col in value_cols:
                    val = row.get(val_col, 0)
                    if isinstance(val, (int, float)):
                        by_date[date_key][val_col] += val
            
            aggregated = []
            for date_key in sorted(by_date.keys()):
                new_row = {date_col: date_key}
                new_row.update(by_date[date_key])
                aggregated.append(new_row)
            
            updated_columns = [date_col] + value_cols
            
            print(f"[AGG] Aggregated {len(data)} rows → {len(aggregated)} rows by date")
            print(f"[AGG] Updated columns from {columns} to {updated_columns}")
            return aggregated, updated_columns
        
        elif name_col and value_cols:
            print(f"[AGG] Grouping by name column: {name_col}")
            by_name = defaultdict(lambda: {col: 0 for col in value_cols})
            
            for row in data:
                name_key = str(row[name_col])
                for val_col in value_cols:
                    val = row.get(val_col, 0)
                    if isinstance(val, (int, float)):
                        by_name[name_key][val_col] += val
            
            aggregated = []
            for name_key in sorted(by_name.keys()):
                new_row = {name_col: name_key}
                new_row.update(by_name[name_key])
                aggregated.append(new_row)
            
            updated_columns = [name_col] + value_cols
            
            print(f"[AGG] Aggregated {len(data)} rows → {len(aggregated)} rows by name")
            print(f"[AGG] Updated columns from {columns} to {updated_columns}")
            return aggregated, updated_columns
    
    return data, columns


def infer_chart_type(data: list, columns: list) -> str:
    """
    Infer best chart type based on data structure.
    """
    if len(columns) == 2:
        return "bar"
    elif len(columns) >= 3:
        return "scatter"
    return "bar"


def generate_matplotlib_code(user_request: str, columns: list, sample_row: dict, chart_type: str ='bar') -> str:
    """
    Use Groq LLM to generate matplotlib visualization code for SPECIFIC chart type.
    
    Args:
        user_request: Original user request
        columns: Column names from query
        sample_row: Sample data row
        chart_type: Type of chart ('pie', 'bar', 'line', 'scatter')
        
    Returns:
        Python code as string
    """
    string_cols = []
    numeric_cols = []
    id_cols = []
    other_cols = []
    
    for col in columns:
        sample = sample_row.get(col)
        if isinstance(sample, str):
            if 'id' in col.lower():
                id_cols.append(col)
            elif 'name' in col.lower() or col.lower() in ('customer', 'flower', 'label', 'category'):
                string_cols.append(col)
            else:
                other_cols.append(col)
        elif isinstance(sample, (int, float)):
            numeric_cols.append(col)
    
    if string_cols:
        col1_name = string_cols[0]  
    elif other_cols:
        col1_name = other_cols[0]
    else:
        col1_name = columns[0]
    
    col2_name = numeric_cols[0] if numeric_cols else (columns[1] if len(columns) > 1 else columns[0])
    
    chart_code_snippets = {
        'pie': f"""ax.pie(col2, labels=col1, autopct="%1.1f%%", colors=colors_list, startangle=90, 
       textprops={{"color": "#E6EDF3", "fontsize": 10, "weight": "bold"}})""",
        'bar': f"""ax.bar(col1, col2, color="#3FB950", edgecolor="white", linewidth=0.5)
ax.set_xlabel("{col1_name}", color="#E6EDF3", fontsize=11, fontweight="bold")
ax.set_ylabel("{col2_name}", color="#E6EDF3", fontsize=11, fontweight="bold")
ax.tick_params(colors="#7D8590", labelsize=9)
plt.xticks(rotation=45, ha="right", color="#E6EDF3")
ax.grid(axis="y", alpha=0.3, color="#30363D")""",
        'line': f"""ax.plot(col1, col2, marker="o", linewidth=2, color="#3FB950", markersize=6)
ax.set_xlabel("{col1_name}", color="#E6EDF3", fontsize=11, fontweight="bold")
ax.set_ylabel("{col2_name}", color="#E6EDF3", fontsize=11, fontweight="bold")
ax.tick_params(colors="#7D8590", labelsize=9)
plt.xticks(rotation=45, ha="right", color="#E6EDF3")
ax.grid(True, alpha=0.3, color="#30363D")""",
        'scatter': f"""ax.scatter(col1, col2, s=100, alpha=0.7, color="#3FB950", edgecolors="white", linewidth=0.5)
ax.set_xlabel("{col1_name}", color="#E6EDF3", fontsize=11, fontweight="bold")
ax.set_ylabel("{col2_name}", color="#E6EDF3", fontsize=11, fontweight="bold")
ax.tick_params(colors="#7D8590", labelsize=9)
plt.xticks(rotation=45, ha="right", color="#E6EDF3")
ax.grid(True, alpha=0.3, color="#30363D")"""
    }
    
    chart_snippet = chart_code_snippets.get(chart_type, chart_code_snippets['bar'])
    
    prompt = f"""COPY THIS TEMPLATE EXACTLY - DO NOT MODIFY THE STRUCTURE.
Only fill in the {col1_name} and {col2_name} values where indicated.
Do NOT change variable names, function calls, or order.

import matplotlib.pyplot as plt
import io

fig, ax = plt.subplots(figsize=(12, 6))
fig.patch.set_facecolor('#0D1117')
ax.set_facecolor('#161B22')

col1 = [row['{col1_name}'] for row in data]
col2 = [row['{col2_name}'] for row in data]

colors_list = ["#3FB950", "#58A6FF", "#D29922", "#F85149", "#FF6B6B", "#4ECDC4", "#FFE66D", "#95E1D3", "#39C5CF", "#A371A7"]

{chart_snippet}

plt.tight_layout()
buf = io.BytesIO()
fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#0D1117')
buf.seek(0)
plt.close(fig)

---
DATA CONTEXT:
- data: list of dicts with keys {columns}
- Sample: {json.dumps(sample_row, default=str)}
- Chart type: {chart_type}

INSTRUCTIONS:
1. Use EXACTLY the template above
2. Replace {col1_name} and {col2_name} with column names from data
3. Do NOT add extra code, comments, or logic beyond the template
4. Output ONLY the Python code, nothing else
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}]
    )
    
    code = response.choices[0].message.content.strip()
    code = code.replace("```python", "").replace("```", "").strip()
    
    print(f"[CHART CODE GENERATED]\n{code[:200]}...")
    return code


def validate_matplotlib_code(code: str) -> tuple:
    """
    Validate generated matplotlib code for safety and correctness.
    Returns: (is_valid, error_message)
    """
    dangerous_patterns = [
        'import os',
        'import subprocess',
        '__import__',
        'eval(',
        'exec(',
        'open(',
        'compile(',
        'globals(',
        'locals(',
    ]
    
    code_lower = code.lower()
    for pattern in dangerous_patterns:
        if pattern in code_lower:
            return False, f"Code contains dangerous pattern: {pattern}"
    
    if 'matplotlib' not in code_lower and 'plt' not in code_lower:
        return False, "Code must use matplotlib"
    
    if 'buf' not in code:
        return False, "Code must create 'buf' variable"
    
    if 'data' not in code:
        return False, "Code must reference 'data' variable from query results"
    
    return True, None


def execute_matplotlib_code(code: str, data: list) -> tuple:
    """
    Execute generated matplotlib code safely with validation.
    
    Returns:
        Tuple of (BytesIO buffer, error_message)
    """
    try:
        is_valid, error = validate_matplotlib_code(code)
        if not is_valid:
            return None, f"Code validation failed: {error}"
        
        code_lines = code.split('\n')
        print(f"[CODE DEBUG] First 5 lines:\n" + "\n".join(code_lines[:5]))
        print(f"[CODE DEBUG] Last 5 lines:\n" + "\n".join(code_lines[-5:]))
        print(f"[DATA] Passing {len(data)} rows of data")
        
        exec_namespace = {
            'plt': plt,
            'io': io,
            'data': data,
            'datetime': datetime,
        }
        
        exec(code, exec_namespace)
        
        if 'buf' in exec_namespace:
            buf = exec_namespace['buf']
            buf.seek(0)
            return buf, None
        else:
            return None, "Generated code didn't create 'buf' variable"
            
    except NameError as e:
        error_msg = str(e)
        print(f"[NAME ERROR] {error_msg}")
        return None, f"Code error - Variable not defined: {error_msg}. Make sure to extract col1 and col2 from data"
    except SyntaxError as e:
        return None, f"Generated code has syntax error: {str(e)}"
    except Exception as e:
        error_type = type(e).__name__
        print(f"[EXCEPTION] {error_type}: {str(e)}")
        return None, f"Chart generation error ({error_type}): {str(e)}"


def generate_chart_with_type(user_request: str, chart_type: str = None) -> tuple:
    """
    Complete workflow WITH CHART TYPE SUPPORT and validation.
    
    Returns: (image_buffer, error_message)
    """
    buf = None
    try:
        print(f"[CHART] Request: {user_request}")
        print(f"[CHART] Chart Type: {chart_type}")
        
        print(f"[LLM] Generating SQL...")
        sql = generate_sql_for_report(user_request)
        print(f"[SQL] {sql[:80]}...")
        
        print("[DB] Executing query...")
        data, columns, error = execute_sql(sql)
        if error:
            return None, f"Database error: {error}"
        
        print(f"[DB] Retrieved {len(data)} rows")
        
        if not chart_type:
            chart_type = suggest_best_chart(columns, data)
            print(f"[CHART] Auto-selected: {chart_type}")
        
        data, columns = aggregate_data_for_chart(data, columns, chart_type)
        print(f"[DB] After aggregation: {len(data)} rows, columns: {columns}")
        
        is_suitable, suggestion, reason = validate_chart_for_data(chart_type, columns, data)
        if not is_suitable:
            print(f"[WARNING] {reason}")
            if suggestion:
                chart_type = suggestion
                print(f"[CHART] Switched to: {chart_type}")
        
        sample_row = data[0] if data else {}
        
        print("[LLM] Generating matplotlib code...")
        chart_code = generate_matplotlib_code(user_request, columns, sample_row, chart_type)
        
        print("[RENDER] Rendering chart...")
        buf, error = execute_matplotlib_code(chart_code, data)
        if error:
            return None, f"Visualization error: {error}"
        
        print("[SUCCESS] Chart generated successfully")
        return buf, None
        
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        if buf:
            buf.close()
        return None, f"Unexpected error: {str(e)}"


def generate_chart_from_request(user_request: str) -> tuple:
    """
    Backward compatible wrapper - auto-detects chart type.
    
    Returns:
        Tuple of (image_buffer, error_message)
    """
    return generate_chart_with_type(user_request, chart_type=None)


def buffer_to_base64(buf: io.BytesIO) -> str:
    """Convert BytesIO buffer to base64 string for embedding in chat."""
    if not buf:
        return None
    try:
        buf.seek(0)
        b64_string = base64.b64encode(buf.read()).decode('utf-8')
        return b64_string
    finally:
        buf.close()
