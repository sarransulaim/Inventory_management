# inventory_app.py
import streamlit as st
import pandas as pd
import av
import cv2
import numpy as np
import base64
from pyzbar import pyzbar
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase

# Database setup
Base = declarative_base()
engine = create_engine('sqlite:///inventory.db')
Session = sessionmaker(bind=engine)
session = Session()

# Database models
class Department(Base):
    __tablename__ = 'departments'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True)
    items = relationship("Item", back_populates="department")

class Item(Base):
    __tablename__ = 'items'
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    barcode = Column(String(50), unique=True)
    quantity = Column(Integer)
    low_stock_threshold = Column(Integer)
    department_id = Column(Integer, ForeignKey('departments.id'))
    last_updated = Column(DateTime, default=datetime.now)
    department = relationship("Department", back_populates="items")

Base.metadata.create_all(engine)

# Barcode scanner processor
class BarcodeProcessor(VideoProcessorBase):
    def __init__(self):
        self.barcode = None

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        detected = pyzbar.decode(img)
        if detected:
            self.barcode = detected[0].data.decode("utf-8")
            (x, y, w, h) = detected[0].rect
            cv2.rectangle(img, (x, y), (x+w, y+h), (0, 255, 0), 2)
        return av.VideoFrame.from_ndarray(img, format="bgr24")

# Helper function
def scan_barcode():
    st.info("Start Scanning...")
    ctx = webrtc_streamer(key="barcode", video_processor_factory=BarcodeProcessor)
    if ctx.video_processor and ctx.video_processor.barcode:
        return ctx.video_processor.barcode
    return None

# Home Page
def home():
    st.title("Inventory Management")

    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("➕ IN", use_container_width=True):
            st.session_state.page = "in"
    with col2:
        if st.button("➖ OUT", use_container_width=True):
            st.session_state.page = "out"
    with col3:
        if st.button("🔎 RETRIEVE", use_container_width=True):
            st.session_state.page = "retrieve"
    with col4:
        if st.button("📋 VIEW INVENTORY", use_container_width=True):
            st.session_state.page = "view"

    st.markdown("---")

# Add Quantity
def inventory_in():
    st.subheader("Add Stock (IN)")
    barcode = scan_barcode()
    if barcode:
        item = session.query(Item).filter_by(barcode=barcode).first()
        if item:
            qty = st.number_input(f"Enter quantity to ADD for '{item.name}':", min_value=1)
            if st.button("Update Stock"):
                item.quantity += qty
                item.last_updated = datetime.now()
                session.commit()
                st.success(f"Added {qty} to '{item.name}'")
        else:
            st.error("Item not found in inventory!")

# Remove Quantity
def inventory_out():
    st.subheader("Remove Stock (OUT)")
    barcode = scan_barcode()
    if barcode:
        item = session.query(Item).filter_by(barcode=barcode).first()
        if item:
            qty = st.number_input(f"Enter quantity to REMOVE from '{item.name}':", min_value=1)
            if st.button("Update Stock"):
                if item.quantity >= qty:
                    item.quantity -= qty
                    item.last_updated = datetime.now()
                    session.commit()
                    st.success(f"Removed {qty} from '{item.name}'")
                else:
                    st.error("Not enough stock to remove!")
        else:
            st.error("Item not found in inventory!")

# Retrieve Info
def retrieve_item():
    st.subheader("Retrieve Item Info")
    barcode = scan_barcode()
    if barcode:
        item = session.query(Item).filter_by(barcode=barcode).first()
        if item:
            st.success(f"Item: {item.name}")
            st.info(f"Quantity: {item.quantity}")
            st.info(f"Department: {item.department.name}")
            st.info(f"Low Stock Threshold: {item.low_stock_threshold}")
        else:
            st.error("Item not found!")

# View Inventory
def view_inventory():
    st.subheader("Current Inventory")
    items = session.query(Item).all()
    if items:
        data = [{
            "Item": i.name,
            "Barcode": i.barcode,
            "Quantity": i.quantity,
            "Department": i.department.name,
            "Low Stock Threshold": i.low_stock_threshold,
            "Last Updated": i.last_updated.strftime("%Y-%m-%d %H:%M")
        } for i in items]
        df = pd.DataFrame(data)
        st.dataframe(df)
    else:
        st.info("No items in inventory yet.")

# Add New Item
def add_new_item():
    st.subheader("Add New Item")
    barcode = scan_barcode()
    if barcode:
        st.success(f"Scanned Barcode: {barcode}")
        departments = session.query(Department).all()
        if not departments:
            st.error("No departments found! Please add departments first.")
            return

        with st.form("item_form"):
            dept = st.selectbox("Select Department", departments, format_func=lambda x: x.name)
            name = st.text_input("Item Name")
            quantity = st.number_input("Initial Quantity", min_value=0)
            threshold = st.number_input("Low Stock Threshold", min_value=1)
            submit = st.form_submit_button("Add Item")

            if submit:
                try:
                    item = Item(
                        name=name,
                        barcode=barcode,
                        quantity=quantity,
                        low_stock_threshold=threshold,
                        department_id=dept.id
                    )
                    session.add(item)
                    session.commit()
                    st.success(f"Item '{name}' added successfully!")
                except:
                    st.error("Barcode must be unique or another error occurred.")

# Department Management
def manage_departments():
    st.subheader("Manage Departments")
    with st.form("add_dept"):
        name = st.text_input("Department Name")
        submit = st.form_submit_button("Add Department")
        if submit:
            if name:
                try:
                    dept = Department(name=name)
                    session.add(dept)
                    session.commit()
                    st.success(f"Department '{name}' added!")
                except:
                    st.error("Department name must be unique.")

# Main app controller
def main():
    if "page" not in st.session_state:
        st.session_state.page = "home"

    if st.session_state.page == "home":
        home()
    elif st.session_state.page == "in":
        inventory_in()
    elif st.session_state.page == "out":
        inventory_out()
    elif st.session_state.page == "retrieve":
        retrieve_item()
    elif st.session_state.page == "view":
        view_inventory()
    elif st.session_state.page == "add":
        add_new_item()
    elif st.session_state.page == "dept":
        manage_departments()

    # Navigation footer
    st.sidebar.title("Navigation")
    if st.sidebar.button("Home"):
        st.session_state.page = "home"
    if st.sidebar.button("Add Item"):
        st.session_state.page = "add"
    if st.sidebar.button("Manage Departments"):
        st.session_state.page = "dept"

if __name__ == "__main__":
    main()
            
