# inventory_app.py

import streamlit as st
import pandas as pd
import av
import cv2
import numpy as np
import altair as alt
import base64
import time
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

class StockHistory(Base):
    __tablename__ = 'stock_history'
    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey('items.id'))
    change = Column(Integer)
    timestamp = Column(DateTime, default=datetime.now)
    note = Column(String(200))

Base.metadata.create_all(engine)

# Barcode scanner processor
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

# Helper function to scan barcode
def scan_barcode(label="Scan Barcode"):
    st.info(label)
    ctx = webrtc_streamer(
        key=label,
        video_processor_factory=BarcodeProcessor,
        media_stream_constraints={"video": True, "audio": False},
    )

    if ctx.video_processor:
        if ctx.video_processor.last_detected_barcode:
            barcode = ctx.video_processor.last_detected_barcode
            st.success(f"Detected Barcode: {barcode}")
            time.sleep(1)
            ctx.stop()
            return barcode
    return None

# Home page
def home():
    st.title("Inventory Management System")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("IN (Add Stock)"):
            handle_in_out(is_in=True)

    with col2:
        if st.button("OUT (Remove Stock)"):
            handle_in_out(is_in=False)

    with col3:
        if st.button("ADD New Item"):
            add_new_item()

    st.markdown("---")
    
    col4, col5 = st.columns(2)

    with col4:
        if st.button("Retrieve Item Info"):
            retrieve_item()

    with col5:
        if st.button("Analytics & Trends"):
            view_analytics()

# Handle IN (add stock) or OUT (remove stock)
def handle_in_out(is_in=True):
    action = "Adding to" if is_in else "Removing from"
    st.header(f"{action} Inventory")
    barcode = scan_barcode(f"{action} Inventory - Scan Barcode")
    if barcode:
        item = session.query(Item).filter_by(barcode=barcode).first()
        if item:
            qty = st.number_input("Enter Quantity", min_value=1, step=1)
            if st.button("Submit"):
                change = qty if is_in else -qty
                item.quantity += change
                item.last_updated = datetime.now()

                # Save history
                history = StockHistory(item_id=item.id, change=change, note="IN" if is_in else "OUT")
                session.add(history)

                session.commit()
                st.success(f"Inventory updated for '{item.name}'!")
        else:
            st.error("Item not found! Please add the item first.")

# Add new item (scan first)
def add_new_item():
    st.header("Add New Item to Inventory")
    barcode = scan_barcode("Add New Item - Scan Barcode")
    if barcode:
        departments = session.query(Department).all()
        if not departments:
            st.warning("Please add at least one department first!")
            return
        
        with st.form("add_item_form"):
            dept = st.selectbox("Select Department", departments, format_func=lambda x: x.name)
            item_name = st.text_input("Item Name")
            quantity = st.number_input("Initial Quantity", min_value=0)
            low_stock = st.number_input("Low Stock Threshold", min_value=1)
            submit = st.form_submit_button("Add Item")

            if submit:
                new_item = Item(
                    name=item_name,
                    barcode=barcode,
                    quantity=quantity,
                    low_stock_threshold=low_stock,
                    department_id=dept.id
                )
                session.add(new_item)
                session.commit()
                st.success(f"Item '{item_name}' added successfully!")

# Retrieve item info
def retrieve_item():
    st.header("Retrieve Item Information")
    barcode = scan_barcode("Retrieve Item Info - Scan Barcode")
    if barcode:
        item = session.query(Item).filter_by(barcode=barcode).first()
        if item:
            st.subheader(f"Item: {item.name}")
            st.write(f"**Department:** {item.department.name}")
            st.write(f"**Current Quantity:** {item.quantity}")
            st.write(f"**Low Stock Threshold:** {item.low_stock_threshold}")
            st.write(f"**Last Updated:** {item.last_updated.strftime('%Y-%m-%d %H:%M')}")

            # Show quantity trend
            history = session.query(StockHistory).filter_by(item_id=item.id).order_by(StockHistory.timestamp).all()
            if history:
                trend_data = pd.DataFrame({
                    "Timestamp": [h.timestamp for h in history],
                    "Quantity Change": [h.change for h in history]
                })
                trend_data["Running Quantity"] = trend_data["Quantity Change"].cumsum() + item.quantity - trend_data["Quantity Change"].sum()

                chart = alt.Chart(trend_data).mark_line(point=True).encode(
                    x="Timestamp:T",
                    y="Running Quantity:Q"
                ).properties(
                    title="Quantity Trend Over Time"
                )
                st.altair_chart(chart, use_container_width=True)
        else:
            st.error("Item not found!")

# View analytics and trends
def view_analytics():
    st.header("Inventory Analytics and Trends")
    items = session.query(Item).all()
    
    if items:
        df = pd.DataFrame([{
            "Item Name": item.name,
            "Department": item.department.name,
            "Quantity": item.quantity,
            "Low Stock Threshold": item.low_stock_threshold,
            "Last Updated": item.last_updated
        } for item in items])

        st.dataframe(df)

        # Inventory levels bar chart
        bar_chart = alt.Chart(df).mark_bar().encode(
            x="Item Name",
            y="Quantity",
            color="Department"
        ).properties(
            title="Inventory Levels by Item",
            width=700,
            height=400
        )
        st.altair_chart(bar_chart, use_container_width=True)

        # Low stock items
        st.subheader("Low Stock Items")
        low_stock_df = df[df["Quantity"] < df["Low Stock Threshold"]]
        if not low_stock_df.empty:
            st.dataframe(low_stock_df)
        else:
            st.success("All stock levels are sufficient.")
    else:
        st.info("No items found.")

# Main app controller
def main():
    menu = ["Home", "Manage Departments", "View Inventory"]
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Home":
        home()
    elif choice == "Manage Departments":
        manage_departments()
    elif choice == "View Inventory":
        view_inventory()

if __name__ == "__main__":
    main()
    
