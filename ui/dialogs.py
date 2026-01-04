"""
UI Dialogs Module (Facade)

This module re-exports dialogs extracted into `ui/modules/dialogs/`.
This structure improves maintainability while preserving backward compatibility.
"""
import streamlit as st

# Re-export modules
from ui.modules.dialogs.plan import show_plan_dialog
from ui.modules.dialogs.analysis import show_analysis_dialog, show_history_dialog
from ui.modules.dialogs.devtools import render_dev_tools
