"""
Plotly Dash dashboard for the Finalto risk management dashboard.

Subscribes to the Quart WebSocket server and visualises:
- Live bid/ask prices for all instruments
- PnL curve over time
- Net position per instrument
- Client yield (spread revenue per client)
- PnL attribution per instrument

Dash is chosen because it is entirely Python based, produces
professional interactive charts out of the box, and supports
real time updates via an interval component.
"""

import json
import asyncio
import threading
import websockets
from dash import Dash, html, dcc, Input, Output, callback
import plotly.graph_objects as go
from config import (
    WEBSOCKET_PORT,
    DASHBOARD_UPDATE_INTERVAL,
)

# --- Shared state ---
latest_data = {
    "prices": {},
    "book": {},
}


def _start_websocket_listener():
    """
    Starts a background thread that maintains a WebSocket connection
    to the Quart server and updates latest_data as messages arrive.
    Automatically reconnects if the connection drops.
    """

    async def _listen():
        uri = f"ws://localhost:{WEBSOCKET_PORT}/ws"
        while True:
            try:
                async with websockets.connect(uri) as ws:
                    print(f"[Dashboard] Connected to WebSocket server at {uri}")
                    async for message in ws:
                        data = json.loads(message)
                        if data.get("type") == "update":
                            latest_data["prices"] = data.get("prices", {})
                            latest_data["book"] = data.get("book", {})
            except Exception as e:
                print(f"[Dashboard] WebSocket error: {e}. Reconnecting in 2s...")
                await asyncio.sleep(2)

    def _run():
        asyncio.run(_listen())

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def _summary_card(card_id: str, label: str) -> html.Div:
    return html.Div([
        html.P(label, style={
            "color": "#aaaaaa",
            "margin": "0 0 8px 0",
            "fontSize": "13px",
            "textTransform": "uppercase",
            "letterSpacing": "1px",
        }),
        html.H2(id=card_id, children="—", style={
            "color": "#ffffff",
            "margin": "0",
            "fontSize": "28px",
        }),
    ], style={
        "backgroundColor": "#16213e",
        "borderRadius": "8px",
        "padding": "20px",
        "flex": "1",
        "borderLeft": "4px solid #e94560",
    })


def _empty_figure(title: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        **_dark_layout(title),
        annotations=[{
            "text": "Waiting for data...",
            "showarrow": False,
            "font": {"color": "#aaaaaa", "size": 14},
        }]
    )
    return fig


def _dark_layout(title: str) -> dict:
    return {
        "title": {
            "text": title,
            "font": {"color": "#ffffff", "size": 16},
        },
        "paper_bgcolor": "#16213e",
        "plot_bgcolor": "#16213e",
        "font": {"color": "#ffffff"},
        "xaxis": {
            "gridcolor": "#0f3460",
            "zerolinecolor": "#0f3460",
        },
        "yaxis": {
            "gridcolor": "#0f3460",
            "zerolinecolor": "#0f3460",
        },
        "margin": {"t": 50, "b": 40, "l": 50, "r": 20},
        "legend": {"font": {"color": "#ffffff"}},
    }


# --- Dash app ---
app = Dash(__name__, title="Finalto Risk Dashboard")

app.layout = html.Div([

    html.Div([
        html.H1("Finalto Risk Management Dashboard",
                style={"color": "#ffffff", "margin": "0", "fontSize": "24px"}),
        html.P("Real-time book monitoring",
               style={"color": "#aaaaaa", "margin": "4px 0 0 0", "fontSize": "14px"}),
    ], style={
        "backgroundColor": "#1a1a2e",
        "padding": "20px 30px",
        "borderBottom": "2px solid #16213e",
    }),

    html.Div([

        html.Div([
            _summary_card("total-pnl", "Total PnL"),
            _summary_card("unrealised-pnl", "Unrealised PnL"),
            _summary_card("realised-pnl", "Realised PnL"),
            _summary_card("spread-revenue", "Spread Revenue"),
        ], style={"display": "flex", "gap": "16px", "marginBottom": "24px"}),

        html.Div([
            dcc.Graph(id="pnl-curve", style={"height": "300px"}),
        ], style={
            "backgroundColor": "#16213e",
            "borderRadius": "8px",
            "padding": "16px",
            "marginBottom": "24px",
        }),

        html.Div([
            html.Div([
                dcc.Graph(id="positions-chart", style={"height": "280px"}),
            ], style={
                "backgroundColor": "#16213e",
                "borderRadius": "8px",
                "padding": "16px",
                "flex": "1",
            }),
            html.Div([
                dcc.Graph(id="client-yield-chart", style={"height": "280px"}),
            ], style={
                "backgroundColor": "#16213e",
                "borderRadius": "8px",
                "padding": "16px",
                "flex": "1",
            }),
        ], style={"display": "flex", "gap": "16px", "marginBottom": "24px"}),

        html.Div([
            html.Div([
                dcc.Graph(id="pnl-attribution-chart", style={"height": "280px"}),
            ], style={
                "backgroundColor": "#16213e",
                "borderRadius": "8px",
                "padding": "16px",
                "flex": "1",
            }),
            html.Div([
                html.H3("Live Prices",
                        style={"color": "#ffffff", "margin": "0 0 12px 0",
                               "fontSize": "16px"}),
                html.Div(id="price-table"),
            ], style={
                "backgroundColor": "#16213e",
                "borderRadius": "8px",
                "padding": "16px",
                "flex": "1",
            }),
        ], style={"display": "flex", "gap": "16px"}),

    ], style={"padding": "24px", "backgroundColor": "#0f3460", "minHeight": "100vh"}),

    dcc.Interval(
        id="interval",
        interval=DASHBOARD_UPDATE_INTERVAL,
        n_intervals=0,
        disabled=False,
    ),

], style={"fontFamily": "Arial, sans-serif", "backgroundColor": "#0f3460"})


# --- Callbacks ---

@callback(
    Output("total-pnl", "children"),
    Output("unrealised-pnl", "children"),
    Output("realised-pnl", "children"),
    Output("spread-revenue", "children"),
    Input("interval", "n_intervals"),
    prevent_initial_call=True,
)
def update_summary_cards(_):
    book = latest_data.get("book", {})
    if not book:
        return "—", "—", "—", "—"

    def _fmt(value: float) -> html.Span:
        colour = "#4CAF50" if value >= 0 else "#e94560"
        return html.Span(f"${value:,.2f}", style={"color": colour})

    return (
        _fmt(book.get("total_pnl", 0)),
        _fmt(book.get("total_unrealised_pnl", 0)),
        _fmt(book.get("total_realised_pnl", 0)),
        html.Span(f"${book.get('total_spread_revenue', 0):,.2f}",
                  style={"color": "#4CAF50"}),
    )


@callback(
    Output("pnl-curve", "figure"),
    Input("interval", "n_intervals"),
    prevent_initial_call=True,
)
def update_pnl_curve(_):
    book = latest_data.get("book", {})
    history = book.get("pnl_history", [])

    if not history:
        return _empty_figure("PnL Curve")

    timestamps = [h["timestamp"] for h in history]
    pnl_values = [h["total_pnl"] for h in history]
    spread_values = [h["total_spread_revenue"] for h in history]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps,
        y=pnl_values,
        name="Total PnL",
        line=dict(color="#e94560", width=2),
        hovertemplate="Time: %{x}<br>PnL: $%{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=timestamps,
        y=spread_values,
        name="Spread Revenue",
        line=dict(color="#4CAF50", width=2, dash="dash"),
        hovertemplate="Time: %{x}<br>Revenue: $%{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(**_dark_layout("PnL Curve Over Time"))
    fig.update_layout(showlegend=True)
    return fig


@callback(
    Output("positions-chart", "figure"),
    Input("interval", "n_intervals"),
    prevent_initial_call=True,
)
def update_positions_chart(_):
    book = latest_data.get("book", {})
    positions = book.get("positions", {})

    if not positions:
        return _empty_figure("Net Positions")

    instruments = list(positions.keys())
    net_sizes = [positions[i]["net_size"] for i in instruments]
    colours = ["#4CAF50" if s >= 0 else "#e94560" for s in net_sizes]

    fig = go.Figure(go.Bar(
        x=instruments,
        y=net_sizes,
        marker_color=colours,
        showlegend=False,
        hovertemplate="Instrument: %{x}<br>Net Size: %{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(**_dark_layout("Net Positions by Instrument"))
    return fig


@callback(
    Output("client-yield-chart", "figure"),
    Input("interval", "n_intervals"),
    prevent_initial_call=True,
)
def update_client_yield_chart(_):
    book = latest_data.get("book", {})
    client_yield = book.get("client_yield", {})

    if not client_yield:
        return _empty_figure("Client Yield")

    clients = list(client_yield.keys())
    yields = [client_yield[c] for c in clients]

    fig = go.Figure(go.Bar(
        x=clients,
        y=yields,
        marker_color="#4CAF50",
        showlegend=False,
        hovertemplate="Client: %{x}<br>Yield: $%{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(**_dark_layout("Client Yield (Spread Revenue)"))
    return fig


@callback(
    Output("pnl-attribution-chart", "figure"),
    Input("interval", "n_intervals"),
    prevent_initial_call=True,
)
def update_pnl_attribution_chart(_):
    book = latest_data.get("book", {})
    positions = book.get("positions", {})

    if not positions:
        return _empty_figure("PnL Attribution")

    instruments = list(positions.keys())
    pnls = [positions[i]["total_pnl"] for i in instruments]
    colours = ["#4CAF50" if p >= 0 else "#e94560" for p in pnls]

    fig = go.Figure(go.Bar(
        x=instruments,
        y=pnls,
        marker_color=colours,
        showlegend=False,
        hovertemplate="Instrument: %{x}<br>PnL: $%{y:,.2f}<extra></extra>",
    ))
    fig.update_layout(**_dark_layout("PnL Attribution by Instrument"))
    return fig


@callback(
    Output("price-table", "children"),
    Input("interval", "n_intervals"),
    prevent_initial_call=True,
)
def update_price_table(_):
    prices = latest_data.get("prices", {})

    if not prices:
        return html.P("Waiting for prices...", style={"color": "#aaaaaa"})

    header = html.Div([
        html.Span("Pair", style={"color": "#aaaaaa", "width": "80px",
                                  "display": "inline-block", "fontSize": "12px"}),
        html.Span("Bid", style={"color": "#aaaaaa", "width": "100px",
                                 "display": "inline-block", "fontSize": "12px"}),
        html.Span("Ask", style={"color": "#aaaaaa", "width": "100px",
                                 "display": "inline-block", "fontSize": "12px"}),
    ], style={"paddingBottom": "8px", "borderBottom": "1px solid #16213e"})

    rows = []
    for instrument, price in prices.items():
        rows.append(html.Div([
            html.Span(instrument, style={"color": "#ffffff", "fontWeight": "bold",
                                          "width": "80px", "display": "inline-block"}),
            html.Span(f"{price['bid']:.5f}", style={"color": "#e94560", "width": "100px",
                                                     "display": "inline-block"}),
            html.Span(f"{price['ask']:.5f}", style={"color": "#4CAF50", "width": "100px",
                                                     "display": "inline-block"}),
        ], style={"padding": "8px 0", "borderBottom": "1px solid #0f3460",
                  "fontSize": "14px"}))

    return [header] + rows


def create_dashboard() -> Dash:
    """
    Initialises the WebSocket listener and returns the Dash app.

    Returns:
        Configured Dash app ready to run.
    """
    _start_websocket_listener()
    app.server.config["PROPAGATE_EXCEPTIONS"] = False
    return app