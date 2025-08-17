"""
Aircraft type database for converting ICAO codes to human-readable names
"""

AIRCRAFT_TYPES = {
    # Boeing
    "B38M": "Boeing 737 MAX 8",
    "B39M": "Boeing 737 MAX 9", 
    "B3XM": "Boeing 737 MAX 10",
    "B737": "Boeing 737",
    "B738": "Boeing 737-800",
    "B739": "Boeing 737-900",
    "B763": "Boeing 767-300",
    "B764": "Boeing 767-400",
    "B772": "Boeing 777-200",
    "B773": "Boeing 777-300",
    "B77L": "Boeing 777-200LR",
    "B77W": "Boeing 777-300ER",
    "B788": "Boeing 787-8 Dreamliner",
    "B789": "Boeing 787-9 Dreamliner",
    "B78X": "Boeing 787-10 Dreamliner",
    
    # Airbus
    "A319": "Airbus A319",
    "A320": "Airbus A320",
    "A321": "Airbus A321",
    "A20N": "Airbus A320neo",
    "A21N": "Airbus A321neo",
    "A332": "Airbus A330-200",
    "A333": "Airbus A330-300",
    "A339": "Airbus A330-900neo",
    "A342": "Airbus A340-200",
    "A343": "Airbus A340-300",
    "A345": "Airbus A340-500",
    "A346": "Airbus A340-600",
    "A359": "Airbus A350-900",
    "A35K": "Airbus A350-1000",
    "A388": "Airbus A380-800",
    
    # Embraer
    "E170": "Embraer 170",
    "E175": "Embraer 175",
    "E190": "Embraer 190",
    "E195": "Embraer 195",
    "E290": "Embraer E-Jet E2",
    
    # Bombardier
    "CRJ2": "Bombardier CRJ-200",
    "CRJ7": "Bombardier CRJ-700",
    "CRJ9": "Bombardier CRJ-900",
    "CRJX": "Bombardier CRJ-1000",
    
    # Other common aircraft
    "DH8D": "Bombardier Dash 8 Q400",
    "AT72": "ATR 72",
    "AT76": "ATR 72-600",
    "SU95": "Sukhoi Superjet 100",
    "C919": "COMAC C919",
    
    # Regional jets
    "F100": "Fokker 100",
    "F70": "Fokker 70",
    "BA46": "BAe 146",
    "RJ85": "Avro RJ85",
    
    # Cargo aircraft
    "B744": "Boeing 747-400",
    "B748": "Boeing 747-8",
    "MD11": "McDonnell Douglas MD-11",
    "A306": "Airbus A300-600",
    
    # Turboprops
    "DH8A": "Bombardier Dash 8-100",
    "DH8B": "Bombardier Dash 8-200", 
    "DH8C": "Bombardier Dash 8-300",
    "SF34": "Saab 340",
    "SF50": "Saab 2000"
}

def get_aircraft_name(icao_code: str) -> str:
    """Convert ICAO aircraft code to human-readable aircraft name"""
    if not icao_code:
        return "Unknown Aircraft"
    
    return AIRCRAFT_TYPES.get(icao_code.upper(), f"Unknown Aircraft ({icao_code})")