import streamlit as st
import pandas as pd
import base64
import av
import cv2
import numpy as np
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

# App pages
def manage_departments():
    st.subheader("📂 Department Management")
    # ... (same department management code from previous version) ...

def manage_items():
    st.subheader("📦 Item Management")
    # ... (same item management code with barcode field) ...

def view_inventory():
    st.subheader("📊 Current Inventory")
    # ... (same inventory view code) ...

def update_stock():
    st.subheader("🔄 Stock Updates")
    # ... (same stock update code) ...

def import_export_data():
    st.subheader("📤 Import/Export Data")
    # ... (same import/export code) ...

def view_stock_history():
    st.subheader("🕰 Stock History")
    # ... (same history view code) ...

def barcode_operations():
    st.subheader("📷 Barcode Scanner")
    ctx = webrtc_streamer(
        key="barcode-scanner",
        video_processor_factory=BarcodeProcessor,
        rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
    )

    if ctx.video_processor:
        barcode = ctx.video_processor.last_detected_barcode
        if barcode:
            st.session_state.last_barcode = barcode

    if 'last_barcode' in st.session_state:
        item = session.query(Item).filter_by(barcode=st.session_state.last_barcode).first()
        if item:
            st.success(f"Scanned: {item.name} (Barcode: {st.session_state.last_barcode})")
            
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📦 Current Stock")
                st.metric("Quantity", item.quantity)
                st.write(f"Low Stock Threshold: {item.low_stock_threshold}")
                
                last_addition = session.query(StockHistory).filter(
                    StockHistory.item_id == item.id,
                    StockHistory.change > 0
                ).order_by(StockHistory.timestamp.desc()).first()
                
                if last_addition:
                    st.write(f"Last added {last_addition.change} on {last_addition.timestamp.date()}")

            with col2:
                with st.form("outgoing_form"):
                    qty = st.number_input("Quantity to deduct", 1, item.quantity)
                    note = st.text_input("Reason")
                    if st.form_submit_button("Confirm Deduction"):
                        item.quantity -= qty
                        history = StockHistory(
                            item_id=item.id,
                            change=-qty,
                            note=f"Deduction: {note}"
                        )
                        session.add(history)
                        session.commit()
                        st.success(f"Updated {item.name} stock to {item.quantity}")
        else:
            st.error("No item found with this barcode")

def main():
    st.set_page_config(
        page_title="Inventory Manager",
        page_icon="📦",
        layout="wide"
    )
    
    st.title("📦 Smart Inventory Manager")
    
    menu = [
        "🏠 Dashboard",
        "📂 Departments",
        "📦 Items",
        "📊 Inventory",
        "🔄 Stock Update",
        "📤 Import/Export",
        "🕰 History",
        "📷 Barcode Scan"
    ]
    
    choice = st.sidebar.selectbox("Navigation", menu)
    
    if choice == "🏠 Dashboard":
        st.subheader("Inventory Dashboard")
        # Add dashboard metrics if needed
    elif choice == "📂 Departments":
        manage_departments()
    elif choice == "📦 Items":
        manage_items()
    elif choice == "📊 Inventory":
        view_inventory()
    elif choice == "🔄 Stock Update":
        update_stock()
    elif choice == "📤 Import/Export":
        import_export_data()
    elif choice == "🕰 History":
        view_stock_history()
    elif choice == "📷 Barcode Scan":
        barcode_operations()

if __name__ == "__main__":
    main()
