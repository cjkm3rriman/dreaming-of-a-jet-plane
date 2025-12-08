"""Debug endpoints for viewing live aircraft provider responses"""

import html
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

AircraftListResult = Tuple[List[Dict[str, Any]], str]
AircraftListFetcher = Callable[[float, float, float, int, Optional[Request], Optional[str]], Awaitable[AircraftListResult]]


def register_test_live_aircraft_routes(
    app: FastAPI,
    *,
    get_user_location_fn: Callable[[Request, Optional[float], Optional[float]], Awaitable[Tuple[float, float]]],
    get_nearby_aircraft_fn: AircraftListFetcher,
    get_provider_definition_fn: Callable[[str], Optional[Dict[str, Any]]],
    provider_override_secret_getter: Callable[[], Optional[str]],
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
                    aircraft, provider_error = await provider_def["fetch"](user_lat, user_lng, 100, 5)
                    if provider_error and not aircraft:
                        error_message = provider_error
        else:
            aircraft, error_message = await get_nearby_aircraft_fn(user_lat, user_lng, 100, 5, request, None)

        if not aircraft and not error_message:
            error_message = "No aircraft found"

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
            return html.escape(str(value or ""))

        def render_row(idx: int, plane: Dict[str, Any]) -> str:
            cells = "".join(
                f"<td>{format_column(column, plane)}</td>"
                for column in ordered_columns
            )
            return f"<tr><td>{idx}</td>{cells}</tr>"

        rows_html = "".join(render_row(i + 1, plane) for i, plane in enumerate(aircraft)) if aircraft else ""

        table_headers = "".join(f"<th>{column.replace('_', ' ').title()}</th>" for column in ordered_columns)
        if not rows_html:
            colspan = 1 + len(ordered_columns)
            rows_html = f'<tr><td colspan="{colspan}">No aircraft data</td></tr>'

        error_html = f'<p class="error">{html.escape(error_message)}</p>' if error_message else ''

        html_body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; background-color: #f8f9fa; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; font-size: 14px; }}
                th {{ background-color: #f2f2f2; }}
                tr:nth-child(even) {{ background-color: #fbfbfb; }}
                .error {{ color: #b71c1c; margin-top: 10px; }}
            </style>
        </head>
        <body>
            <h1>Live Aircraft Debug</h1>
            <p>Lat: {user_lat}, Lng: {user_lng}, Provider: {html.escape(provider_label)}</p>
            {error_html}
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
