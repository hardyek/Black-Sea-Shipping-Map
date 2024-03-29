import asyncio
import websockets
import json
from datetime import datetime
import pytz
import psycopg2

try:                                                                                            # Connect to the database
    connection = psycopg2.connect(database = "vessel_tracking",
                                host="localhost",
                                port="5432",
                                user="postgres",
                                password="postgres")
    print("Database connected successfully")
except:
    print("Failed to connect to database")

                                                                                                # Initialising the subscription message and the pending vessels dictionary
pending_vessels = {}

subscription_message = {"APIKey": "0c041a2989078bc8d9c0295059a9eeaf0c7f5186",
            "BoundingBoxes": [[[50.008747, 21.141895],[35.997054, 59.637987]]],
            "FilterMessageTypes": ["PositionReport", "ShipStaticData"]}

async def connect_ais_stream():                                                                 # Subscribe and recieve messages from the websocket
    while True:
        try:
            async with websockets.connect("wss://stream.aisstream.io/v0/stream") as websocket:
                subscription_message_json = json.dumps(subscription_message)
            
                await websocket.send(subscription_message_json)

                count = 0
                print("Websocket connection established")
                async for message_json in websocket:
                    count += 1
                    message = json.loads(message_json)
                    message_type = message["MessageType"]

                    if message_type == "PositionReport":                                                 # Handle the PositionReport message type
                        ais_message = message["Message"]["PositionReport"]
                        handle_position_report(ais_message)

                    elif message_type == "ShipStaticData":                                               # Handle the ShipStaticData messsage type
                        ais_message = message["Message"]["ShipStaticData"]
                        handle_ship_static_data(ais_message)

                    else:                                                                                # Handle other message type.
                        print(f"Unrecognised message type: {message_type}")
                    
                    if count == 100:
                        count = 0
                        print(f""" 100 Messages Handled - {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} """)

        except(websockets.exceptions.ConnectionClosedError):
            print("Connection to websocket server closed unexpectedly. Retrying in 5 seconds...")
            await asyncio.sleep(5)
            continue

        except Exception as e:
            print(f"An error occurred: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
            continue
                
def handle_position_report(message):
    vessel_id = message["UserID"]

    #__f"Position Report received, MMSI: {vessel_id}")

    exists_query = "SELECT id FROM vessels WHERE id = %s;"

    with connection.cursor() as exists_cursor:
        exists_cursor.execute(exists_query, (vessel_id,))
        exists = exists_cursor.fetchone() is not None

    #__f"MMSI: {vessel_id} exists in database: {exists}")

    if exists:
        update_query = "UPDATE vessels SET lat = %s, long = %s, status = %s, cog = %s, sog = %s, timestamp = %s WHERE id = %s;"
        with connection.cursor() as update_cursor:
            update_cursor.execute(
                update_query,
                (
                    message["Latitude"],
                    message["Longitude"],
                    message["NavigationalStatus"],
                    message["Cog"],
                    message["Sog"],
                    datetime.now().astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    vessel_id,
                ),
            )

        connection.commit()

        #__f"Successfully updated MMSI: {vessel_id}")

    else:
        if vessel_id in pending_vessels:
            #__f"MMSI: {vessel_id} found in pending vessels")
            if pending_vessels[vessel_id]["Type"] == "ShipStaticData":
                #__"Pending ShipStaticData found")
                add_new_entry(message, pending_vessels[vessel_id]["Message"])
        else:
            pending_vessels[vessel_id] = {"Message": message, "Type": "PositionReport"}
            #__f"Added new entry to pending vessels, MMSI: {vessel_id}")

def handle_ship_static_data(message):
    vessel_id = message["UserID"]

    #__f"Ship Static Data received, MMSI: {vessel_id}")

    exists_query = "SELECT id FROM vessels WHERE id = %s;"

    with connection.cursor() as exists_cursor:
        exists_cursor.execute(exists_query, (vessel_id,))
        exists = exists_cursor.fetchone() is not None

    #__f"MMSI: {vessel_id} exists in database: {exists}")

    if exists:
        update_query = "UPDATE vessels SET name = %s, imo = %s, type = %s, length = %s WHERE id = %s;"
        with connection.cursor() as update_cursor:
            update_cursor.execute(
                update_query,
                (
                    message["Name"],
                    message["ImoNumber"],
                    message["Type"],
                    (message["Dimension"]["A"] + message["Dimension"]["B"]),
                    vessel_id,
                ),
            )

        connection.commit()

        #__f"Successfully updated MMSI: {vessel_id}")

    else:
        if vessel_id in pending_vessels:
            #__f"MMSI: {vessel_id} found in pending vessels")
            if pending_vessels[vessel_id]["Type"] == "PositionReport":
                #__"Pending PositionReport found")
                add_new_entry(pending_vessels[vessel_id]["Message"], message)
        else:
            pending_vessels[vessel_id] = {"Message": message, "Type": "ShipStaticData"}
            #__f"Added new entry to pending vessels, MMSI: {vessel_id}")

def add_new_entry(position_report, ship_static_data):                                           # Function to handle the addition of a new entry to the table

    create_query = f"INSERT INTO vessels (id,name,imo,type,length,lat,long,status,cog,sog,timestamp) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"

    with connection.cursor() as create_cursor:
        create_cursor.execute(create_query, (ship_static_data['UserID'],ship_static_data["Name"],ship_static_data["ImoNumber"],ship_static_data["Type"],(ship_static_data["Dimension"]["A"] + ship_static_data["Dimension"]["B"]), position_report["Latitude"], position_report["Longitude"], position_report["NavigationalStatus"], position_report["Cog"], position_report["Sog"], datetime.now().astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S"),))

    connection.commit()

    #__f""" Added new entry MMSI: {ship_static_data['UserID']} """)

if __name__ == "__main__":
    asyncio.run(asyncio.run(connect_ais_stream()))