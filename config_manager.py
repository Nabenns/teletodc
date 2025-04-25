import asyncio
import argparse
from loguru import logger

from bot import TelegramForwarder
from db_schema import list_configurations, delete_configuration

async def list_config():
    """List all configured forwarding rules."""
    bot = TelegramForwarder()
    configs = await list_configurations(bot.db_path)
    
    if not configs:
        print("No configurations found.")
        return
    
    print("\nCurrent Configurations:")
    print("----------------------")
    for group_name, topic_name, webhook_url, topic_id in configs:
        print(f"Topic ID: {topic_id}")
        print(f"Group: {group_name}")
        print(f"Topic: {topic_name}")
        print(f"Webhook: {webhook_url}")
        print("----------------------")

async def add_config_interactive():
    """Add a new forwarding configuration interactively."""
    print("\nMenambah Konfigurasi Baru")
    print("-------------------------")
    
    # Get group information
    while True:
        try:
            group_id = input("Masukkan Group ID (contoh: -1002578936671): ").strip()
            group_id = int(group_id)
            break
        except ValueError:
            print("Error: Group ID harus berupa angka!")
    
    group_name = input("Masukkan nama grup: ").strip()
    
    # Get topic information
    while True:
        try:
            topic_id = input("Masukkan Topic ID (contoh: 2): ").strip()
            topic_id = int(topic_id)
            break
        except ValueError:
            print("Error: Topic ID harus berupa angka!")
    
    topic_name = input("Masukkan nama topic: ").strip()
    
    # Get webhook URL
    webhook_url = input("Masukkan webhook URL: ").strip()
    
    # Optional description
    description = input("Masukkan deskripsi (optional, tekan Enter untuk skip): ").strip()
    if not description:
        description = None
    
    # Confirm
    print("\nKonfirmasi konfigurasi:")
    print(f"Group ID: {group_id}")
    print(f"Group Name: {group_name}")
    print(f"Topic ID: {topic_id}")
    print(f"Topic Name: {topic_name}")
    print(f"Webhook URL: {webhook_url}")
    if description:
        print(f"Description: {description}")
    
    confirm = input("\nApakah konfigurasi sudah benar? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Dibatalkan.")
        return
    
    # Add configuration
    bot = TelegramForwarder()
    try:
        await bot.add_configuration(
            group_id=group_id,
            group_name=group_name,
            topic_id=topic_id,
            topic_name=topic_name,
            webhook_url=webhook_url,
            description=description
        )
        print(f"\nBerhasil menambahkan konfigurasi untuk topic {topic_name} di grup {group_name}")
    except Exception as e:
        print(f"Error: {str(e)}")

async def delete_config_interactive():
    """Delete a configuration interactively."""
    # First show all configurations
    bot = TelegramForwarder()
    configs = await list_configurations(bot.db_path)
    
    if not configs:
        print("Tidak ada konfigurasi yang bisa dihapus.")
        return
    
    print("\nKonfigurasi yang tersedia:")
    print("-------------------------")
    for i, (group_name, topic_name, webhook_url, topic_id) in enumerate(configs, 1):
        print(f"{i}. Topic ID: {topic_id}")
        print(f"   Group: {group_name}")
        print(f"   Topic: {topic_name}")
        print(f"   Webhook: {webhook_url}")
        print("-------------------------")
    
    while True:
        try:
            choice = input("\nPilih nomor konfigurasi yang ingin dihapus (atau 'q' untuk batal): ").strip()
            if choice.lower() == 'q':
                print("Dibatalkan.")
                return
            
            idx = int(choice) - 1
            if 0 <= idx < len(configs):
                topic_id = configs[idx][3]  # Get topic_id from tuple
                if await delete_configuration(bot.db_path, topic_id):
                    print(f"Berhasil menghapus konfigurasi dengan Topic ID {topic_id}")
                else:
                    print(f"Gagal menghapus konfigurasi dengan Topic ID {topic_id}")
                break
            else:
                print("Pilihan tidak valid!")
        except ValueError:
            print("Masukkan nomor yang valid!")

async def main_menu():
    """Interactive main menu."""
    while True:
        print("\nTelegram Topic Forwarder - Menu Utama")
        print("1. Lihat semua konfigurasi")
        print("2. Tambah konfigurasi baru")
        print("3. Hapus konfigurasi")
        print("4. Keluar")
        
        choice = input("\nPilih menu (1-4): ").strip()
        
        if choice == "1":
            await list_config()
        elif choice == "2":
            await add_config_interactive()
        elif choice == "3":
            await delete_config_interactive()
        elif choice == "4":
            print("Terima kasih!")
            break
        else:
            print("Pilihan tidak valid!")

def main():
    if len(sys.argv) > 1:
        # If arguments are provided, use the old CLI interface
        parser = argparse.ArgumentParser(description="Telegram Topic Forwarder Configuration")
        subparsers = parser.add_subparsers(dest="command", help="Commands")
        
        list_parser = subparsers.add_parser("list", help="List all configurations")
        
        add_parser = subparsers.add_parser("add", help="Add a new configuration")
        add_parser.add_argument("--group-id", type=int, required=True, help="Telegram group ID")
        add_parser.add_argument("--group-name", required=True, help="Telegram group name")
        add_parser.add_argument("--topic-id", type=int, required=True, help="Topic ID")
        add_parser.add_argument("--topic-name", required=True, help="Topic name")
        add_parser.add_argument("--webhook-url", required=True, help="Webhook URL")
        add_parser.add_argument("--description", help="Optional description")
        
        delete_parser = subparsers.add_parser("delete", help="Delete a configuration")
        delete_parser.add_argument("--topic-id", type=int, required=True, help="Topic ID to delete")
        
        args = parser.parse_args()
        
        if args.command == "list":
            asyncio.run(list_config())
        elif args.command == "add":
            asyncio.run(add_config(
                group_id=args.group_id,
                group_name=args.group_name,
                topic_id=args.topic_id,
                topic_name=args.topic_name,
                webhook_url=args.webhook_url,
                description=args.description
            ))
        elif args.command == "delete":
            asyncio.run(delete_config(args.topic_id))
        else:
            parser.print_help()
    else:
        # If no arguments, use the interactive menu
        asyncio.run(main_menu())

if __name__ == "__main__":
    import sys
    main() 