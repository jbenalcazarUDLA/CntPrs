from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_
from typing import List, Optional
from datetime import datetime, timedelta
import pandas as pd
from fastapi.responses import StreamingResponse
import io

from .. import models, schemas
from ..database import get_db

router = APIRouter()

def filter_base_query(db: Session, start_date: str, end_date: str, cameras: List[int] = None, timeslots: List[str] = None):
    query = db.query(models.HistoricoConteo).filter(
        models.HistoricoConteo.fecha_registro >= start_date,
        models.HistoricoConteo.fecha_registro <= end_date
    )
    if cameras:
        query = query.filter(models.HistoricoConteo.source_id.in_(cameras))
        
    return query

def time_to_sortable_hour(time_str):
    # '18:38:00' -> '18:00'
    try:
        return time_str[:2] + ':00'
    except:
        return "00:00"

@router.get("/dashboard")
def get_dashboard_data(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    cameras: str = Query(None, description="Comma separated camera IDs"),
    time_slots: str = Query(None, description="Comma separated time ranges, e.g. 06:00-12:00,12:00-18:00"),
    db: Session = Depends(get_db)
):
    camera_ids = [int(c) for c in cameras.split(",")] if cameras else None
    slots = time_slots.split(",") if time_slots else None

    # BASE QUERY
    query = db.query(
        models.HistoricoConteo.id,
        models.HistoricoConteo.source_id,
        models.VideoSource.name.label('source_name'),
        models.HistoricoConteo.fecha_registro,
        models.HistoricoConteo.hora_apertura,
        models.HistoricoConteo.hora_cierre,
        models.HistoricoConteo.total_in,
        models.HistoricoConteo.total_out
    ).join(
        models.VideoSource, models.VideoSource.id == models.HistoricoConteo.source_id
    ).filter(
        models.HistoricoConteo.fecha_registro >= start_date,
        models.HistoricoConteo.fecha_registro <= end_date
    )

    if camera_ids:
        query = query.filter(models.HistoricoConteo.source_id.in_(camera_ids))

    results = query.all()

    # Process in memory (or using Pandas) as SQLite date/time functions are limited
    # We use Pandas for easier aggregation and time slot filtering
    if not results:
         return {
            "kpis": {
                "total_in": 0,
                "total_out": 0,
                "aforo_promedio": 0,
                "peak_day": None,
                "stay_rate": 0
            },
            "charts": {
                "time_series": {},
                "compare_locations": {},
                "compare_periods": {},
                "accumulated": {}
            }
        }

    df = pd.DataFrame([r._asdict() for r in results])
    
    # Apply Time Slots filter
    if slots:
        # Complex logic to see if hora_apertura falls into any of the slots
        # For simplicity, let's keep it simple: exact overlap or starting within
        mask = pd.Series([False] * len(df))
        for slot in slots:
            try:
                start_s, end_s = slot.split('-')
                # We check if hora_apertura is between start_s and end_s
                slot_mask = (df['hora_apertura'] >= start_s) & (df['hora_apertura'] <= end_s)
                mask = mask | slot_mask
            except:
                pass
        if mask.any():
            df = df[mask]
        else:
            df = pd.DataFrame(columns=df.columns)

    if df.empty:
        return {
             "kpis": {"total_in": 0, "total_out": 0, "aforo_promedio": 0, "peak_day": None, "stay_rate": 0},
             "charts": {"time_series": {}, "compare_locations": {}, "compare_periods": {}, "accumulated": {}}
        }

    # KPIs
    total_in = int(df['total_in'].sum())
    total_out = int(df['total_out'].sum())
    
    # Aforo pormedio (Promedio por franja horaria / o por registro)
    aforo_promedio = round(df['total_in'].mean(), 2)

    # Dia de mayor flujo (IN + OUT)
    daily_totals = df.groupby('fecha_registro')[['total_in', 'total_out']].sum()
    daily_totals['total_flow'] = daily_totals['total_in'] + daily_totals['total_out']
    peak_day = daily_totals['total_flow'].idxmax() if not daily_totals.empty else None

    # Tasa Permanencia (Diferencia acumulada / Total In - Simplificado)
    # We estimate remaining people as total_in - total_out. Over time this measures retention.
    # Rate = (total_in - total_out) / total_in
    if total_in > 0:
        stay_rate = round(((total_in - total_out) / total_in) * 100, 2)
        stay_rate = max(0, stay_rate) # No negative rate
    else:
        stay_rate = 0

    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    delta = end_dt - start_dt
    prev_end_dt = start_dt - timedelta(days=1)
    prev_start_dt = prev_end_dt - delta
    
    prev_query = db.query(
        func.sum(models.HistoricoConteo.total_in).label('total_in'),
        func.sum(models.HistoricoConteo.total_out).label('total_out')
    ).filter(
        models.HistoricoConteo.fecha_registro >= prev_start_dt.strftime("%Y-%m-%d"),
        models.HistoricoConteo.fecha_registro <= prev_end_dt.strftime("%Y-%m-%d")
    )
    if camera_ids:
        prev_query = prev_query.filter(models.HistoricoConteo.source_id.in_(camera_ids))
    
    # Handle time slots for prev_query if we want to be exact. 
    # Since sqlite doesn't easily filter by time slot without complex conditions, and doing pandas again is slow, 
    # we'll approximate the trend or leave it as total day trend.
    # To keep it exact, we might skip time_slots for trend or leave it as general. 
    prev_res = prev_query.first()
    prev_total_in = int(prev_res.total_in or 0) if prev_res else 0
    prev_total_out = int(prev_res.total_out or 0) if prev_res else 0

    def calc_trend(curr, prev):
        if prev == 0 and curr == 0: return 0
        if prev == 0: return 100
        return round(((curr - prev) / prev) * 100, 1)

    trends = {
        "total_in": calc_trend(total_in, prev_total_in),
        "total_out": calc_trend(total_out, prev_total_out),
        "aforo_promedio": calc_trend(total_in, prev_total_in) # Mean scales directly
    }

    kpis = {
        "total_in": total_in,
        "total_out": total_out,
        "aforo_promedio": aforo_promedio,
        "peak_day": peak_day,
        "stay_rate": stay_rate,
        "trends": trends
    }

    # Charts
    # 1. Time Series (Traffic trends, X: date, Y: IN, multi-camera overlay)
    time_series = {"labels": [], "datasets": []}
    dates = sorted(df['fecha_registro'].unique())
    time_series["labels"] = dates
    
    for cam_name in df['source_name'].unique():
        cam_data = df[df['source_name'] == cam_name].groupby('fecha_registro')['total_in'].sum().reindex(dates, fill_value=0)
        time_series["datasets"].append({
            "label": f"{cam_name} (IN)",
            "data": cam_data.tolist()
        })

    # 2. Compare Locations (Bar Chart: Which has more traffic)
    loc_totals = df.groupby('source_name')[['total_in', 'total_out']].sum()
    compare_locations = {
        "labels": loc_totals.index.tolist(),
        "datasets": [
            {
                "label": "Ingresos (IN)",
                "data": loc_totals['total_in'].tolist()
            },
            {
                 "label": "Salidas (OUT)",
                 "data": loc_totals['total_out'].tolist()
            }
        ]
    }

    # 3. Compare Periods (This period vs previous period of same length)
    compare_periods = {
        "labels": ["Ingresos Totales"],
        "datasets": [
            {
                 "label": f"Previo ({prev_start_dt.strftime('%b %d')} - {prev_end_dt.strftime('%b %d')})",
                 "data": [prev_total_in]
            },
            {
                 "label": f"Actual ({start_dt.strftime('%b %d')} - {end_dt.strftime('%b %d')})",
                 "data": [total_in]
            }
        ]
    }

    # 4. Accumulated Analysis (Heatmap proxy: Average traffic per Day of Week)
    df['date_obj'] = pd.to_datetime(df['fecha_registro'])
    df['day_of_week'] = df['date_obj'].dt.day_name()
    day_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    # group by day of week
    dow_totals = df.groupby('day_of_week')['total_in'].mean().reindex(day_order, fill_value=0)
    
    accumulated = {
        "labels": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"],
        "datasets": [{
            "label": "Promedio de Ingreso Diario",
            "data": dow_totals.tolist()
        }]
    }

    return {
        "kpis": kpis,
        "charts": {
            "time_series": time_series,
            "compare_locations": compare_locations,
            "compare_periods": compare_periods,
            "accumulated": accumulated
        }
    }

@router.get("/export")
def export_csv(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    cameras: str = Query(None, description="Comma separated camera IDs"),
    time_slots: str = Query(None, description="Comma separated time ranges"),
    db: Session = Depends(get_db)
):
    camera_ids = [int(c) for c in cameras.split(",")] if cameras else None
    
    query = db.query(
        models.HistoricoConteo.id,
        models.VideoSource.name.label('Sede/Camara'),
        models.HistoricoConteo.fecha_registro.label('Fecha'),
        models.HistoricoConteo.hora_apertura.label('Hora_Apertura'),
        models.HistoricoConteo.hora_cierre.label('Hora_Cierre'),
        models.HistoricoConteo.total_in.label('Ingresos'),
        models.HistoricoConteo.total_out.label('Salidas')
    ).join(
        models.VideoSource, models.VideoSource.id == models.HistoricoConteo.source_id
    ).filter(
        models.HistoricoConteo.fecha_registro >= start_date,
        models.HistoricoConteo.fecha_registro <= end_date
    )

    if camera_ids:
        query = query.filter(models.HistoricoConteo.source_id.in_(camera_ids))

    results = query.all()
    df = pd.DataFrame([r._asdict() for r in results])
    
    if slots := time_slots:
        slots_list = slots.split(",")
        mask = pd.Series([False] * len(df))
        for slot in slots_list:
            try:
                start_s, end_s = slot.split('-')
                slot_mask = (df['Hora_Apertura'] >= start_s) & (df['Hora_Apertura'] <= end_s)
                mask = mask | slot_mask
            except:
                pass
        if not df.empty and mask.any():
            df = df[mask]
        else:
            df = pd.DataFrame(columns=df.columns)

    stream = io.StringIO()
    df.to_csv(stream, index=False)
    
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=reporte_trafico_{start_date}_{end_date}.csv"
    return response

