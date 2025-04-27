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
import time

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

class StockHistory(Base):
    __tablename__ = 'stock_history'
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey('items.id'))
    change = Column(Integer)
    timestamp = Column(DateTime, default=datetime.now)
    note = Column(String(200))

Base.metadata.create_all(engine)

# Barcode scanner component
class BarcodeProcessor(VideoProcessorBase):
    def __init__(self):
        self.last_detected_barcode = None
    
    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        detected_barcodes = pyzbar.decode(img)
        
        if detected_barcodes:
            self.last_detected_barcode = detected_barcodes[0].data.decode("utf-8")
            for barcode in detected_barcodes:
                (x, y, w, h) = barcode.rect
                cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        else:
            self.last_detected_barcode = None
            
        return av.VideoFrame.from_ndarray(img, format="bgr24")

# Helper functions
def get_table_download_link(df):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="inventory.csv">Download CSV</a>'

def color_stock(val, threshold):
    if val < threshold:
        return 'background-color: #ffcccc'  # light red
    elif val < threshold + 5:
        return 'background-color: #fff3cd'  # light yellow
    else:
        return 'background-color: #d4edda'  # light green

# App pages
def manage_departments():
    st.header("Department Management")
    
    with st.expander("Add New Department"):
        with st.form("department_form"):
            dept_name = st.text_input("Department Name")
            submit = st.form_submit_button("Add Department")
            
            if submit:
                if not dept_name:
                    st.error("Please enter a department name")
                else:
                    try:
                        new_dept = Department(name=dept_name)
                        session.add(new_dept)
                        session.commit()
                        st.success(f"Department '{dept_name}' added!")
                    except:
                        session.rollback()
                        st.error("Department name already exists")

    with st.expander("Edit/Delete Departments"):
        departments = session.query(Department).all()
        if departments:
            selected_dept = st.selectbox("Select Department", 
                                        departments, format_func=lambda x: x.name)
            
            with st.form("edit_dept_form"):
                new_name = st.text_input("New Name", value=selected_dept.name)
                col1, col2 = st.columns(2)
                with col1:
                    update_btn = st.form_submit_button("Update")
                with col2:
                    delete_btn = st.form_submit_button("Delete")
                
                if update_btn:
                    selected_dept.name = new_name
                    session.commit()
                    st.success("Department updated!")
                if delete_btn:
                    session.delete(selected_dept)
                    session.commit()
                    st.success("Department deleted!")
        else:
            st.info("No departments found")

def manage_items():
    st.header("Item Management")
    
    departments = session.query(Department).all()
    if not departments:
        st.warning("Create departments first")
        return
    
    with st.expander("Add New Item"):
        with st.form("item_form"):
            dept = st.selectbox("Department", departments, format_func=lambda x: x.name)
            item_name = st.text_input("Item Name")
            barcode = st.text_input("Barcode")
            quantity = st.number_input("Initial Quantity", min_value=0)
            low_stock = st.number_input("Low Stock Threshold", min_value=1)
            submit = st.form_submit_button("Add Item")
            
            if submit:
                if not item_name or not barcode:
                    st.error("Please fill all required fields")
                else:
                    try:
                        new_item = Item(
                            name=item_name,
                            barcode=barcode,
                            quantity=quantity,
                            low_stock_threshold=low_stock,
                            department_id=dept.id
                        )
                        session.add(new_item)
                        session.commit()
                        st.success("Item added successfully!")
                    except:
                        session.rollback()
                        st.error("Barcode must be unique")

    with st.expander("Edit/Delete Items"):
        items = session.query(Item).all()
        if items:
            selected_item = st.selectbox("Select Item", 
                                       items, format_func=lambda x: f"{x.name} ({x.department.name})")
            
            with st.form("edit_item_form"):
                new_name = st.text_input("Name", value=selected_item.name)
                new_barcode = st.text_input("Barcode", value=selected_item.barcode)
                new_qty = st.number_input("Quantity", value=selected_item.quantity)
                new_threshold = st.number_input("Low Stock Threshold", 
                                                value=selected_item.low_stock_threshold)
                
                col1, col2 = st.columns(2)
                with col1:
                    update_btn = st.form_submit_button("Update")
                with col2:
                    delete_btn = st.form_submit_button("Delete")
                
                if update_btn:
                    selected_item.name = new_name
                    selected_item.barcode = new_barcode
                    selected_item.quantity = new_qty
                    selected_item.low_stock_threshold = new_threshold
                    selected_item.last_updated = datetime.now()
                    session.commit()
                    st.success("Item updated!")
                if delete_btn:
                    session.delete(selected_item)
                    session.commit()
                    st.success("Item deleted!")
        else:
            st.info("No items found")

def view_inventory():
    st.header("Current Inventory")
    
    items = session.query(Item).all()
    if items:
        inventory_data = []
        for item in items:
            inventory_data.append({
                "Department": item.department.name,
                "Item Name": item.name,
                "Barcode": item.barcode,
                "Quantity": item.quantity,
                "Low Stock Threshold": item.low_stock_threshold,
                "Last Updated": item.last_updated.strftime("%Y-%m-%d %H:%M")
            })
        
        df = pd.DataFrame(inventory_data)
        
        # Color the stock levels
        styled_df = df.style.apply(
            lambda x: [color_stock(v, x["Low Stock Threshold"]) for v in x["Quantity"]],
            axis=1
        )
        
        st.dataframe(styled_df)

        # CSV Download link
        st.markdown(get_table_download_link(df), unsafe_allow_html=True)

        # Low stock alerts
        st.subheader("Low Stock Alerts")
        low_stock = df[df["Quantity"] < df["Low Stock Threshold"]]
        if not low_stock.empty:
            st.warning("Some items are below their low stock thresholds!")
            st.dataframe(low_stock)
        else:
            st.success("All stock levels are sufficient.")
    else:
        st.info("No items in inventory yet.")

def scan_barcode():
    st.header("Scan Item Barcode")
    ctx = webrtc_streamer(key="barcode", video_processor_factory=BarcodeProcessor)

    if ctx.video_processor and ctx.video_processor.last_detected_barcode:
        barcode = ctx.video_processor.last_detected_barcode
        st.success(f"Detected Barcode: {barcode}")
        
        # Audio beep
        st.audio("https://www.soundjay.com/buttons/sounds/button-3.mp3", format="audio/mp3")

        # Lookup item
        item = session.query(Item).filter_by(barcode=barcode).first()
        if item:
            st.info(f"Item Found: {item.name} ({item.quantity} available)")

            with st.form("stock_update_form"):
                qty_change = st.number_input("Change in Quantity (+ to add, - to reduce)", value=0)
                note = st.text_input("Note (optional)")
                submit = st.form_submit_button("Update Stock")

                if submit:
                    item.quantity += qty_change
                    item.last_updated = datetime.now()
                    session.add(StockHistory(item_id=item.id, change=qty_change, note=note))
                    session.commit()
                    st.success("Stock updated successfully!")
                    time.sleep(1)
                    st.experimental_rerun()
        else:
            st.error("Item not found in database.")

# Sidebar navigation
st.sidebar.title("Inventory Management")
page = st.sidebar.radio("Go to", ["Manage Departments", "Manage Items", "View Inventory", "Scan Barcode"])

if page == "Manage Departments":
    manage_departments()
elif page == "Manage Items":
    manage_items()
elif page == "View Inventory":
    view_inventory()
elif page == "Scan Barcode":
    scan_barcode()
        
