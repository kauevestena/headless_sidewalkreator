#!/usr/bin/env python3
"""
Create a simple visualization of the crossing generation issue.
"""

import matplotlib.pyplot as plt
import numpy as np

def create_grid_diagram():
    """Create a diagram showing the 2x2 grid and crossing issue."""
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    
    # Left plot: Grid layout with intersections
    ax1.set_title("2×2 Grid: 9 Intersections vs 8 Expected Crossings", 
                  fontsize=14, fontweight='bold')
    
    # Draw grid lines
    # Vertical lines: x=1,2,3 from y=0 to y=4
    for i in [1, 2, 3]:
        ax1.plot([i, i], [0, 4], 'b-', linewidth=2, label='Grid lines' if i == 1 else '')
    
    # Horizontal lines: y=1,2,3 from x=0 to x=4  
    for i in [1, 2, 3]:
        ax1.plot([0, 4], [i, i], 'b-', linewidth=2)
    
    # Mark intersection points
    intersections = [(1,1), (1,2), (1,3), (2,1), (2,2), (2,3), (3,1), (3,2), (3,3)]
    for i, (x, y) in enumerate(intersections):
        ax1.plot(x, y, 'ro', markersize=10, label='Intersections' if i == 0 else '')
        ax1.annotate(f'{i+1}', (x, y), xytext=(3, 3), textcoords='offset points', 
                    fontsize=9, fontweight='bold', color='white')
    
    ax1.set_xlim(-0.5, 4.5)
    ax1.set_ylim(-0.5, 4.5)
    ax1.set_xlabel("X coordinate")
    ax1.set_ylabel("Y coordinate")
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    ax1.set_aspect('equal')
    
    # Add text annotations
    ax1.text(0.5, 4.2, "Grid lines: 6 total", fontsize=10, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightblue"))
    ax1.text(0.5, 3.8, "Intersections: 9 total", fontsize=10, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightcoral"))
    
    # Right plot: Mathematical analysis
    ax2.set_title("Mathematical Analysis", fontsize=14, fontweight='bold')
    ax2.text(0.05, 0.95, "Formula: C = 4wh - 2w - 2h", fontsize=16, fontweight='bold', 
             transform=ax2.transAxes, family='monospace', 
             bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow"))
    
    ax2.text(0.05, 0.85, "For 2×2 grid:", fontsize=14, fontweight='bold', transform=ax2.transAxes)
    ax2.text(0.05, 0.80, "C = 4×2×2 - 2×2 - 2×2", fontsize=12, family='monospace', transform=ax2.transAxes)
    ax2.text(0.05, 0.75, "C = 16 - 4 - 4 = 8", fontsize=12, family='monospace', transform=ax2.transAxes)
    ax2.text(0.05, 0.70, "Expected: 8 crossings", fontsize=12, fontweight='bold', 
             color='green', transform=ax2.transAxes)
    
    ax2.text(0.05, 0.60, "Current Algorithm Results:", fontsize=14, fontweight='bold', transform=ax2.transAxes)
    ax2.text(0.05, 0.55, "• Direct API: 9 crossings ❌", fontsize=12, transform=ax2.transAxes, color='red')
    ax2.text(0.05, 0.50, "• Full workflow: 9 crossings ❌", fontsize=12, transform=ax2.transAxes, color='red')
    ax2.text(0.05, 0.45, "• Difference: +1 crossing", fontsize=12, transform=ax2.transAxes, color='red')
    
    ax2.text(0.05, 0.35, "Root Cause:", fontsize=14, fontweight='bold', transform=ax2.transAxes)
    ax2.text(0.05, 0.30, "Algorithm generates 1 crossing", fontsize=12, transform=ax2.transAxes)
    ax2.text(0.05, 0.26, "per intersection (9 total)", fontsize=12, transform=ax2.transAxes)
    ax2.text(0.05, 0.22, "Formula expects fewer crossings", fontsize=12, transform=ax2.transAxes)
    ax2.text(0.05, 0.18, "based on urban planning logic", fontsize=12, transform=ax2.transAxes)
    
    ax2.text(0.05, 0.08, "Solution: Modify algorithm to be", fontsize=12, fontweight='bold', 
             transform=ax2.transAxes, color='blue')
    ax2.text(0.05, 0.04, "selective about crossing placement", fontsize=12, fontweight='bold', 
             transform=ax2.transAxes, color='blue')
    
    ax2.set_xlim(0, 1)
    ax2.set_ylim(0, 1)
    ax2.axis('off')
    
    plt.tight_layout()
    plt.savefig('crossing_analysis_diagram.png', dpi=150, bbox_inches='tight')
    print("📊 Diagram saved as 'crossing_analysis_diagram.png'")
    
    return fig

if __name__ == "__main__":
    create_grid_diagram()
    plt.show()