import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime

# Color scheme
BG = '#0D1117'
TEXT = '#E6EDF3'
MUTED = '#7D8590'
GREEN = '#3FB950'
RED = '#F85149'
BLUE = '#58A6FF'
YELLOW = '#D29922'
CYAN = '#39C5CF'

def generate_report(data):
    """
    Generate a simple 4-chart report.
    Returns PNG bytes.
    """
    
    revenue = data["revenue"]
    stock = data["stock"]
    status = data["status"]
    customers = data["customers"]
    summary = data["summary"]
    
    # Create figure with 4 subplots
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(
        2, 2, figsize=(14, 10), facecolor=BG
    )
    fig.suptitle('Flower Shop - Business Report', 
                 fontsize=18, fontweight='bold', 
                 color=GREEN, y=0.98)
    
    # ── Chart 1: Revenue by Flower (Bar) ──────────────────
    names = [r[0] for r in revenue]
    values = [float(r[1]) for r in revenue]
    colors_revenue = [GREEN, CYAN, YELLOW, BLUE, RED][:len(names)]
    
    ax1.bar(names, values, color=colors_revenue, edgecolor='white', linewidth=0.5)
    ax1.set_title('Revenue by Flower', fontsize=11, fontweight='bold', color=TEXT, loc='left')
    ax1.set_ylabel('Revenue ($)', color=MUTED, fontsize=9)
    ax1.set_facecolor('#161B22')
    ax1.tick_params(colors=MUTED, labelsize=8)
    ax1.grid(axis='y', alpha=0.3, color='#30363D')
    
    # Add value labels on bars
    for i, (name, value) in enumerate(zip(names, values)):
        ax1.text(i, value, f'${value:,.0f}', ha='center', va='bottom', 
                color=MUTED, fontsize=8)
    
    # ── Chart 2: Stock Levels (Horizontal Bar) ────────────
    s_names = [s[0] for s in stock]
    s_values = [s[1] for s in stock]
    s_colors = [RED if q < 20 else GREEN for q in s_values]
    
    ax2.barh(s_names, s_values, color=s_colors, edgecolor='white', linewidth=0.5)
    ax2.set_title('Stock Levels', fontsize=11, fontweight='bold', color=TEXT, loc='left')
    ax2.set_xlabel('Units in Stock', color=MUTED, fontsize=9)
    ax2.set_facecolor('#161B22')
    ax2.tick_params(colors=MUTED, labelsize=8)
    ax2.grid(axis='x', alpha=0.3, color='#30363D')
    
    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=GREEN, label='OK (≥20)'),
        Patch(facecolor=RED, label='Low (<20)')
    ]
    ax2.legend(handles=legend_elements, loc='lower right', fontsize=8)
    
    # ── Chart 3: Order Status (Pie/Donut) ─────────────────
    st_labels = [s[0].capitalize() for s in status]
    st_values = [s[1] for s in status]
    colors_status = [GREEN, YELLOW, RED, BLUE][:len(st_labels)]
    
    wedges, texts, autotexts = ax3.pie(
        st_values, labels=st_labels, autopct='%1.0f%%',
        colors=colors_status, startangle=90,
        wedgeprops=dict(edgecolor='#0D1117', linewidth=1.5)
    )
    ax3.set_title('Order Status', fontsize=11, fontweight='bold', color=TEXT, loc='left')
    ax3.set_facecolor(BG)
    
    # Style pie chart text
    for text in texts:
        text.set_color(TEXT)
        text.set_fontsize(8)
    for autotext in autotexts:
        autotext.set_color('#0D1117')
        autotext.set_fontweight('bold')
        autotext.set_fontsize(8)
    
    # ── Chart 4: Top Customers (Horizontal Bar) ──────────
    top_customers = customers[:8]
    cust_names = [c[0] for c in top_customers][::-1]
    cust_values = [float(c[2]) for c in top_customers][::-1]
    
    ax4.barh(cust_names, cust_values, color=BLUE, edgecolor='white', linewidth=0.5)
    ax4.set_title('Top Customers by Spend', fontsize=11, fontweight='bold', color=TEXT, loc='left')
    ax4.set_xlabel('Total Spent ($)', color=MUTED, fontsize=9)
    ax4.set_facecolor('#161B22')
    ax4.tick_params(colors=MUTED, labelsize=8)
    ax4.grid(axis='x', alpha=0.3, color='#30363D')
    
    # Add value labels
    for i, value in enumerate(cust_values):
        ax4.text(value, i, f'  ${value:,.0f}', va='center', color=MUTED, fontsize=8)
    
    # ── Summary Info at Top ───────────────────────────────
    summary_text = (
        f"Total Revenue: ${summary['total_revenue']:,.2f} | "
        f"Orders: {summary['total_orders']} | "
        f"Customers: {summary['total_customers']} | "
        f"Low Stock: {summary['low_stock_count']}"
    )
    fig.text(0.5, 0.02, summary_text, ha='center', fontsize=9, 
             color=MUTED, style='italic')
    
    # Adjust layout
    plt.tight_layout(rect=[0, 0.04, 1, 0.96])
    
    # Save to buffer
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, facecolor=BG)
    buf.seek(0)
    plt.close(fig)
    return buf
