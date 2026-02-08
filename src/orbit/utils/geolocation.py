"""Browser geolocation utilities for getting user's current location."""

import streamlit as st
import streamlit.components.v1 as components


def get_geolocation_component():
    """
    Render HTML/JS component to get user's current location.

    Returns coordinates via Streamlit's component value system.
    """
    html_code = """
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {
                margin: 0;
                padding: 10px;
                font-family: sans-serif;
            }
            .location-btn {
                background-color: #FF4B4B;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
            }
            .location-btn:hover {
                background-color: #E63946;
            }
            .location-btn:disabled {
                background-color: #ccc;
                cursor: not-allowed;
            }
            .status {
                margin-top: 10px;
                font-size: 12px;
                color: #666;
            }
        </style>
    </head>
    <body>
        <button id="getLocationBtn" class="location-btn" onclick="getLocation()">
            📍 Use Current Location
        </button>
        <div id="status" class="status"></div>

        <script>
            const Streamlit = window.parent.Streamlit || window.Streamlit;

            function getLocation() {
                const statusEl = document.getElementById('status');
                const btn = document.getElementById('getLocationBtn');

                if (!navigator.geolocation) {
                    statusEl.textContent = '❌ Geolocation not supported by your browser';
                    Streamlit.setComponentValue({error: 'not_supported'});
                    return;
                }

                btn.disabled = true;
                statusEl.textContent = '⏳ Getting your location...';

                navigator.geolocation.getCurrentPosition(
                    function(position) {
                        const coords = {
                            lat: position.coords.latitude,
                            lon: position.coords.longitude,
                            accuracy: position.coords.accuracy
                        };
                        statusEl.textContent = `✓ Location found! (±${Math.round(coords.accuracy)}m accuracy)`;
                        Streamlit.setComponentValue(coords);
                        btn.disabled = false;
                    },
                    function(error) {
                        let errorMsg = 'Unknown error';
                        switch(error.code) {
                            case error.PERMISSION_DENIED:
                                errorMsg = '❌ Location access denied. Please enable location permissions.';
                                Streamlit.setComponentValue({error: 'denied'});
                                break;
                            case error.POSITION_UNAVAILABLE:
                                errorMsg = '❌ Location unavailable';
                                Streamlit.setComponentValue({error: 'unavailable'});
                                break;
                            case error.TIMEOUT:
                                errorMsg = '❌ Location request timed out';
                                Streamlit.setComponentValue({error: 'timeout'});
                                break;
                        }
                        statusEl.textContent = errorMsg;
                        btn.disabled = false;
                    },
                    {
                        enableHighAccuracy: true,
                        timeout: 10000,
                        maximumAge: 0
                    }
                );
            }
        </script>
    </body>
    </html>
    """

    return components.html(html_code, height=80)
