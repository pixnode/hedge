import os
from py_clob_client.client import ClobClient
from config import config

def generate_creds():
    print("="*50)
    print("POLYMARKET API CREDENTIAL GENERATOR")
    print("="*50)
    
    if not config.POLYMARKET_PRIVATE_KEY:
        print("ERROR: POLYMARKET_PRIVATE_KEY tidak ditemukan di .env")
        return

    try:
        # Inisialisasi client hanya dengan Private Key untuk melakukan derivasi
        client = ClobClient(
            host=config.CLOB_HOST,
            key=config.POLYMARKET_PRIVATE_KEY,
            chain_id=137,
            signature_type=1,
            funder=config.POLYMARKET_PRIVATE_KEY
        )
        
        print("Sedang melakukan derivasi API Key dari Private Key...")
        creds = client.create_or_derive_api_creds()
        
        print("\n[!] BERHASIL! Silakan salin kredensial ini ke .env Anda:\n")
        print(f"POLY_API_KEY={creds.api_key}")
        print(f"POLY_API_SECRET={creds.api_secret}")
        print(f"POLY_API_PASSPHRASE={creds.api_passphrase}")
        print("\n" + "="*50)
        
    except Exception as e:
        print(f"ERROR: Terjadi kegagalan saat generate API Key - {e}")

if __name__ == "__main__":
    generate_creds()
