"""Debug endpoints for viewing live aircraft provider responses"""

import html
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

AircraftListResult = Tuple[List[Dict[str, Any]], str]
AircraftListFetcher = Callable[[float, float, float, int, Optional[Request], Optional[str]], Awaitable[AircraftListResult]]
SelectDiverseAircraftFn = Callable[[List[Dict[str, Any]], Optional[float], Optional[float]], List[Dict[str, Any]]]
CalculateMinDistanceToRouteFn = Callable[[float, float, float, float, float, float], float]


def register_test_live_aircraft_routes(
    app: FastAPI,
    *,
    get_user_location_fn: Callable[[Request, Optional[float], Optional[float]], Awaitable[Tuple[float, float]]],
    get_nearby_aircraft_fn: AircraftListFetcher,
    get_provider_definition_fn: Callable[[str], Optional[Dict[str, Any]]],
    provider_override_secret_getter: Callable[[], Optional[str]],
    select_diverse_aircraft_fn: SelectDiverseAircraftFn,
    calculate_min_distance_to_route_fn: CalculateMinDistanceToRouteFn,
    get_airport_by_iata_fn: Callable[[str], Optional[Dict[str, Any]]],
) -> None:
    """Attach the live aircraft debugging endpoint to the FastAPI app"""

    @app.get("/test/live-aircraft", response_class=HTMLResponse)
    async def test_live_aircraft_endpoint(
        request: Request,
        lat: float = None,
        lng: float = None,
        provider: Optional[str] = None,
        secret: Optional[str] = None,
    ):
        secret_value = provider_override_secret_getter()
        if not secret_value:
            return HTMLResponse("<h1>Provider override secret is not configured.</h1>", status_code=403)

        if secret != secret_value:
            return HTMLResponse("<h1>Invalid secret.</h1>", status_code=403)

        user_lat, user_lng = await get_user_location_fn(request, lat, lng)

        selected_provider = provider or request.query_params.get("aircraft_provider")
        selected_provider = selected_provider.lower() if selected_provider else None

        provider_label = "auto"
        aircraft: List[Dict[str, Any]] = []
        error_message = ""

        # Always fetch directly from provider to get full aircraft list (not diversity-selected)
        if selected_provider:
            provider_def = get_provider_definition_fn(selected_provider)
            if not provider_def:
                error_message = f"Unknown provider: {html.escape(selected_provider)}"
            else:
                is_configured, config_error = provider_def["is_configured"]()
                if not is_configured:
                    error_message = config_error or f"{provider_def.get('display_name', selected_provider)} is not configured"
                else:
                    provider_label = provider_def.get("display_name", selected_provider)
                    # Fetch more aircraft to display full list (not just diversity-selected ones)
                    aircraft, provider_error = await provider_def["fetch"](user_lat, user_lng, 100, 30)
                    if provider_error and not aircraft:
                        error_message = provider_error
        else:
            # Try providers in sequence to get full list (bypass get_nearby_aircraft diversity selection)
            from ..aircraft_providers import get_provider_names
            provider_names = get_provider_names()

            for provider_name in provider_names:
                provider_def = get_provider_definition_fn(provider_name)
                if not provider_def:
                    continue

                is_configured, config_error = provider_def["is_configured"]()
                if not is_configured:
                    continue

                try:
                    provider_label = provider_def.get("display_name", provider_name)
                    aircraft, provider_error = await provider_def["fetch"](user_lat, user_lng, 100, 30)
                    if aircraft:
                        break  # Use first provider that returns data
                    if provider_error:
                        error_message = provider_error
                except Exception as e:
                    error_message = f"Provider {provider_name} error: {e}"
                    continue

        if not aircraft and not error_message:
            error_message = "No aircraft found"

        # Apply diversity selection to see what would be chosen
        selected_aircraft = []
        if aircraft:
            selected_aircraft = select_diverse_aircraft_fn(aircraft.copy(), user_lat, user_lng)

        # Calculate minimum route distance for each aircraft
        for plane in aircraft:
            origin_iata = plane.get("origin_airport")
            dest_iata = plane.get("destination_airport")

            if origin_iata and dest_iata:
                origin_airport = get_airport_by_iata_fn(origin_iata)
                dest_airport = get_airport_by_iata_fn(dest_iata)

                if origin_airport and dest_airport:
                    origin_lat = origin_airport.get("lat")
                    origin_lon = origin_airport.get("lon")
                    dest_lat = dest_airport.get("lat")
                    dest_lon = dest_airport.get("lon")

                    if all([origin_lat, origin_lon, dest_lat, dest_lon]):
                        min_route_distance = calculate_min_distance_to_route_fn(
                            user_lat, user_lng,
                            origin_lat, origin_lon,
                            dest_lat, dest_lon
                        )
                        plane["min_route_distance_km"] = round(min_route_distance)
                    else:
                        plane["min_route_distance_km"] = None
                else:
                    plane["min_route_distance_km"] = None
            else:
                plane["min_route_distance_km"] = None

        preferred_columns = [
            "callsign",
            "flight_number",
            "airline_name",
            "aircraft",
            "aircraft_registration",
            "origin_airport",
            "origin_city",
            "destination_airport",
            "destination_city",
            "destination_country",
            "distance_km",
            "min_route_distance_km",
            "eta",
            "updated",
        ]

        column_set = {key for plane in aircraft for key in plane.keys()}
        ordered_columns = [col for col in preferred_columns if col in column_set]
        for column in sorted(column_set):
            if column not in ordered_columns:
                ordered_columns.append(column)

        def format_column(column: str, plane: Dict[str, Any]) -> str:
            value = plane.get(column)
            if column == "updated" and value:
                try:
                    updated_dt = datetime.fromtimestamp(float(value), tz=timezone.utc)
                    seconds_ago = int((datetime.now(timezone.utc) - updated_dt).total_seconds())
                    value = f"{seconds_ago} sec ago"
                except Exception:
                    pass
            elif column == "min_route_distance_km" and value is not None:
                # Color code the route distance
                if value > 500:
                    return f'<span style="color: #d32f2f; font-weight: bold;">{value} km ❌</span>'
                else:
                    return f'<span style="color: #388e3c; font-weight: bold;">{value} km ✅</span>'
            return html.escape(str(value or ""))

        # Check if aircraft is selected by diversity algorithm
        selected_ids = {plane.get("flight_id") for plane in selected_aircraft}

        def render_row(idx: int, plane: Dict[str, Any]) -> str:
            cells = []
            for column in ordered_columns:
                cell_content = format_column(column, plane)
                # Add special class for route distance column
                cell_class = ' class="route-distance"' if column == "min_route_distance_km" else ''
                cells.append(f"<td{cell_class}>{cell_content}</td>")

            is_selected = plane.get("flight_id") in selected_ids
            row_class = ' class="selected"' if is_selected else ''
            selection_marker = "✅ " if is_selected else ""
            return f"<tr{row_class}><td>{selection_marker}{idx}</td>{''.join(cells)}</tr>"

        rows_html = "".join(render_row(i + 1, plane) for i, plane in enumerate(aircraft)) if aircraft else ""

        table_headers = "".join(f"<th>{column.replace('_', ' ').title()}</th>" for column in ordered_columns)
        if not rows_html:
            colspan = 1 + len(ordered_columns)
            rows_html = f'<tr><td colspan="{colspan}">No aircraft data</td></tr>'

        error_html = f'<p class="error">{html.escape(error_message)}</p>' if error_message else ''

        # Create selected aircraft summary
        selected_summary_html = ""
        if selected_aircraft:
            selected_items = []
            for i, plane in enumerate(selected_aircraft, 1):
                flight_id = plane.get("flight_number") or plane.get("callsign") or plane.get("flight_id") or "Unknown"

                # Origin info
                origin = plane.get("origin_city") or plane.get("origin_airport") or "Unknown"
                origin_country = plane.get("origin_country") or ""
                origin_str = f"{html.escape(origin)}, {html.escape(origin_country)}" if origin_country else html.escape(origin)

                # Destination info
                dest = plane.get("destination_city") or plane.get("destination_airport") or "Unknown"
                dest_country = plane.get("destination_country") or ""
                dest_str = f"{html.escape(dest)}, {html.escape(dest_country)}" if dest_country else html.escape(dest)

                # Route
                route_str = f"{origin_str} → {dest_str}"

                # Distances
                dest_dist_km = plane.get("destination_distance_from_user_km")
                dest_dist_str = f" (dest {dest_dist_km:.0f}km from user)" if dest_dist_km else ""

                airline = plane.get("airline_name") or plane.get("airline_icao") or "Unknown"

                position_label = "1st (closest passenger)" if i == 1 else "2nd (cargo/private if available)" if i == 2 else "3rd (diverse destination)"
                selected_items.append(
                    f"<li><strong>Position {i}</strong> ({position_label}): {html.escape(flight_id)} - {route_str}{html.escape(dest_dist_str)} [{html.escape(airline)}]</li>"
                )

            selected_summary_html = f"""
            <div class="selected-summary">
                <h2>🎯 Selected by Diversity Algorithm (3 aircraft)</h2>
                <p>These aircraft would be presented to the user based on geographic diversity, cargo/private inclusion, and distance filtering:</p>
                <ol>
                    {"".join(selected_items)}
                </ol>
            </div>
            """

        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; background-color: #f8f9fa; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 14px; }}
                th {{ background-color: #f2f2f2; }}
                tr:nth-child(even) {{ background-color: #fbfbfb; }}
                tr.selected {{ background-color: #e8f5e9 !important; font-weight: bold; }}
                .error {{ color: #b71c1c; margin-top: 10px; }}
                .route-distance {{
                    background-color: #fffde7;
                    font-weight: bold;
                }}
                .selected-summary {{
                    background-color: #e3f2fd;
                    border-left: 4px solid #2196F3;
                    padding: 15px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
                .selected-summary h2 {{ margin-top: 0; color: #1565C0; }}
                .selected-summary ol {{ margin: 10px 0; }}
                .selected-summary li {{ margin: 8px 0; }}
            </style>
        </head>
        <body>
            <h1>Live Aircraft Debug</h1>
            <p>Lat: {user_lat}, Lng: {user_lng}, Provider: {html.escape(provider_label)}</p>
            {error_html}
            {selected_summary_html}
            <h2>All Aircraft ({len(aircraft)} found)</h2>
            <p>✅ = Selected by diversity algorithm | <strong>Min Route Distance</strong> = Closest the flight path comes to your location (✅ &lt;500km, ❌ &gt;500km)</p>
            <table>
                <tr>
                    <th>#</th>
                    {table_headers if ordered_columns else ''}
                </tr>
                {rows_html}
            </table>
        </body>
        </html>
        """

        return HTMLResponse(html_body)
