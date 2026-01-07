#!/usr/bin/env python3
"""
Launcher for Sapient React+FastAPI Application

This file replaces the Streamlit workflow with the new React+FastAPI version.
The original Streamlit app is preserved in app_streamlit.py.
"""

import os
import sys

if __name__ == "__main__":
    os.execvp("python", ["python", "server.py"])
else:
    import subprocess
    subprocess.Popen(["python", "server.py"])
    import streamlit as st
    st.set_page_config(page_title="Sapient", page_icon="📈")
    st.title("🇦🇺 Sapient Portfolio Optimizer")
    st.info("The application is now running on the new React interface. Please refresh the page.")
    st.markdown("If you don't see the new interface, please wait a moment and refresh.")
