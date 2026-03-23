"""
Dynamic Report Generation System
- Converts natural language requests to SQL queries
- Generates matplotlib visualizations on-the-fly
- Integrates with chat interface
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
    Validate SQL query for safety.
    - Must start with SELECT
    - No dangerous keywords (INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER)
    """
    dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'TRUNCATE', 'ALTER', 'CREATE']
    sql_upper = sql.strip().upper()
    
    if not sql_upper.startswith('SELECT'):
        return False
    
    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            return False
    
    return True


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


def generate_sql_for_report(user_request: str) -> str:
    """
    Use Groq LLM to convert natural language request to SQL query.
    
    WHY: Updated to enforce PostgreSQL ROUND() syntax with ::numeric cast
    
    Args:
        user_request: Natural language description (e.g., "Show revenue by flower") 
    Returns:
        SQL query string
    """
    prompt = f"""You are a PostgreSQL expert for a flower shop database.

Database Schema:
{DB_SCHEMA}

User Request: "{user_request}"

Generate a SELECT query that fulfills this request.

CRITICAL Rules:
- Return ONLY the raw SQL query — no explanation, no markdown, no code blocks
- Use proper JOINs when needed
- Use LOWER() ONLY for VARCHAR/TEXT comparisons - NEVER on numeric values
- For date filtering:
  * Use DATE comparison: WHERE o.order_date >= CURRENT_DATE - INTERVAL '7 days'
  * Or use: WHERE DATE(o.order_date) = CURRENT_DATE
  * Do NOT use LOWER() on EXTRACT() results - they are numeric
  * Do NOT use LOWER() on day() function - it is numeric

CRITICAL - ROUNDING/CALCULATIONS (PostgreSQL rules):
- ALWAYS cast aggregates to ::numeric before ROUND()
- WRONG: ROUND(SUM(o.quantity) * f.price, 2)
- CORRECT: ROUND(SUM(o.quantity)::numeric * f.price::numeric, 2)
- CORRECT: ROUND(CAST(SUM(o.total_price) AS numeric), 2)
- When multiplying columns, cast each to ::numeric first

- Ensure column names are descriptive (they'll be used for visualization)
- Limit results to reasonable numbers (100 rows max)

Date Range Examples:
- "last week": WHERE o.order_date >= CURRENT_DATE - INTERVAL '7 days'
- "last month": WHERE o.order_date >= CURRENT_DATE - INTERVAL '30 days'
- "today": WHERE DATE(o.order_date) = CURRENT_DATE
- "specific date": WHERE DATE(o.order_date) = '2026-03-19'

Examples (NOTE the ::numeric casts):
- Request: "Show revenue by flower type"
  Response: SELECT f.name AS flower, ROUND(SUM(o.total_price)::numeric, 2) AS revenue FROM orders o JOIN flowers f ON o.flower_id = f.id GROUP BY f.name ORDER BY revenue DESC

- Request: "Top 5 customers by spending"
  Response: SELECT c.name, COUNT(o.id) AS orders, ROUND(SUM(o.total_price)::numeric, 2) AS total_spent FROM customers c LEFT JOIN orders o ON c.id = o.customer_id GROUP BY c.id, c.name ORDER BY total_spent DESC LIMIT 5

- Request: "Sales for last week"
  Response: SELECT f.name AS flower, SUM(o.quantity) AS quantity_sold, ROUND(SUM(o.total_price)::numeric, 2) AS revenue FROM orders o JOIN flowers f ON o.flower_id = f.id WHERE o.order_date >= CURRENT_DATE - INTERVAL '7 days' GROUP BY f.name ORDER BY revenue DESC

- Request: "Total sales by flower in last 30 days"
  Response: SELECT f.name AS flower, ROUND(SUM(o.quantity)::numeric * f.price::numeric, 2) AS total_sales FROM orders o JOIN flowers f ON o.flower_id = f.id WHERE o.order_date >= CURRENT_DATE - INTERVAL '30 days' GROUP BY f.name, f.price ORDER BY total_sales DESC
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}]
    )
    
    sql = response.choices[0].message.content.strip()
    sql = sql.replace("```sql", "").replace("```", "").strip()
    
    if 'ROUND' in sql.upper():
        if 'ROUND(' in sql and '::numeric' not in sql:
            print(f"[WARNING] ROUND() without ::numeric cast detected. SQL: {sql[:100]}")
    
    if not validate_sql_syntax(sql):
        raise ValueError("Generated SQL failed safety validation")
    
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


def infer_chart_type(data: list, columns: list) -> str:
    """
    Infer best chart type based on data structure.
    """
    if len(columns) == 2:
        return "bar"
    elif len(columns) >= 3:
        return "scatter"
    return "bar"


def generate_matplotlib_code(user_request: str, columns: list, sample_row: dict) -> str:
    """
    Use Groq LLM to generate matplotlib visualization code.
    
    Args:
        user_request: Original user request
        columns: Column names from query
        sample_row: Sample data row
        
    Returns:
        Python code as string
    """
    numeric_columns = []
    text_columns = []
    for col in columns:
        sample_val = sample_row.get(col)
        if isinstance(sample_val, (int, float)):
            numeric_columns.append(col)
        else:
            text_columns.append(col)
    
    prompt = f"""You are a matplotlib expert. Generate ONLY executable Python code.

DATA STRUCTURE:
- 'data' is a list of dictionaries (dicts)
- Each dict has these keys: {columns}
- Sample: {json.dumps(sample_row, default=str)}
- Text columns: {text_columns}
- Numeric columns: {numeric_columns}

USER REQUEST: "{user_request}"

INSTRUCTIONS:
1. Extract values from 'data' using list comprehension or loops
2. Define all variables before using them
3. Only use variables defined in your code
4. Format numbers: use f-string like f'{{x:,.2f}}' or str(x)
5. Create visualization using matplotlib

TEMPLATE (adapt this):
```python
import matplotlib.pyplot as plt
import io

fig, ax = plt.subplots(figsize=(12, 6))
fig.patch.set_facecolor('#0D1117')
ax.set_facecolor('#161B22')

# Extract data from 'data' variable
col1 = [row['{columns[0]}'] for row in data]
col2 = [row['{columns[1]}'] for row in data] if len(data) > 0 else []

# Create chart
ax.bar(col1, col2, color='#3FB950', edgecolor='white', linewidth=0.5)
ax.set_xlabel('{columns[0]}', color='#E6EDF3')
ax.set_ylabel('{columns[1]}', color='#E6EDF3')
ax.tick_params(colors='#7D8590', labelsize=9)
ax.grid(axis='y', alpha=0.3, color='#30363D')

# Add value labels on bars
for i, v in enumerate(col2):
    ax.text(i, v, f'{{v:.0f}}', ha='center', va='bottom', color='#7D8590', fontsize=8)

plt.title('{user_request}', fontsize=14, fontweight='bold', color='#E6EDF3')
plt.tight_layout()
buf = io.BytesIO()
fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='#0D1117')
buf.seek(0)
plt.close(fig)
```

CRITICAL RULES:
- Every variable must be defined before use
- Use col1, col2, etc. for extracted columns
- Never reference undefined 'value', 'row', 'x', 'y' variables
- For loops must define loop variables: for i, v in enumerate():
- All variables used in loops must exist
- Import statements at top only
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}]
    )
    
    code = response.choices[0].message.content.strip()
    code = code.replace("```python", "").replace("```", "").strip()
    return code


def validate_matplotlib_code(code: str) -> tuple:
    """
    Validate generated matplotlib code for safety before execution.
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
        return None, f"Code error - undefined variable: {str(e)}"
    except SyntaxError as e:
        return None, f"Generated code has syntax error: {str(e)}"
    except Exception as e:
        error_type = type(e).__name__
        return None, f"Chart generation error ({error_type}): {str(e)}"


def generate_chart_from_request(user_request: str) -> tuple:
    """
    Complete workflow: request → SQL → data → visualization → buffer
    Comprehensive error handling and resource cleanup.
    
    Returns:
        Tuple of (image_buffer, error_message)
    """
    buf = None
    try:
        if not detect_report_request(user_request):
            return None, "This doesn't seem to be a report request."
        
        try:
            print(f"[LLM] Generating SQL for: {user_request}")
            sql = generate_sql_for_report(user_request)
            print(f"[SQL] Generated: {sql[:100]}...")
        except ValueError as ve:
            return None, f"SQL Generation error: {str(ve)}"
        
        print("[DB] Executing query...")
        data, columns, error = execute_sql(sql)
        if error:
            return None, f"Database error: {error}"
        
        print(f"[DB] Retrieved {len(data)} rows with columns: {columns}")
        
        sample_row = data[0] if data else {}
        
        print("[LLM] Generating visualization code...")
        chart_code = generate_matplotlib_code(user_request, columns, sample_row)
        print(f"[CODE] Generated {len(chart_code)} chars of code")
        
        print("[RENDER] Creating visualization...")
        buf, error = execute_matplotlib_code(chart_code, data)
        if error:
            return None, f"Visualization error: {error}"
        
        print("[SUCCESS] Chart generated")
        return buf, None
        
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        if buf:
            buf.close()
        return None, f"Unexpected error: {str(e)}"


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
