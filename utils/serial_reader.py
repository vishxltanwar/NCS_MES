import serial

from .scanner import clean_scan_data


def read_scan_line(
    port: str = "COM1",
    baudrate: int = 115200,
    timeout: float = 2
) -> str:
    """
    Open the barcode scanner serial port and return one cleaned scan line.

    Defaults match Honeywell 1950 RS-232 on COM1 at 115200 baud, 8N1.
    """
    with serial.Serial(
        port=port,
        baudrate=baudrate,
        bytesize=serial.EIGHTBITS,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        timeout=timeout,
    ) as scanner:
        raw_line = scanner.readline()

    if isinstance(raw_line, bytes):
        raw_line = raw_line.decode("utf-8", errors="replace")

    return clean_scan_data(raw_line)
