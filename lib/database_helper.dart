import 'dart:io';
import 'package:flutter/services.dart';
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart';
import 'models/product.dart';

class DatabaseHelper {
  static final DatabaseHelper _instance = DatabaseHelper._internal();
  factory DatabaseHelper() => _instance;
  DatabaseHelper._internal();

  Database? _db;

  Future<Database> get database async {
    if (_db != null) return _db!;
    _db = await _init();
    return _db!;
  }

  Future<Database> _init() async {
    final dir = await getApplicationDocumentsDirectory();
    final localPath = join(dir.path, 'shop.db');

    if (!File(localPath).existsSync()) {
      final data = await rootBundle.load('assets/shop.db');
      await File(localPath).writeAsBytes(data.buffer.asUint8List());
    }

    return openDatabase(
      localPath,
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE IF NOT EXISTS inventory (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name      TEXT    NOT NULL,
            category       TEXT    NOT NULL DEFAULT 'General',
            price          REAL    NOT NULL,
            stock_quantity INTEGER NOT NULL DEFAULT 0,
            image_path     TEXT,
            image_data     TEXT
          )
        ''');
        await db.execute('''
          CREATE TABLE IF NOT EXISTS history (
            bill_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT    NOT NULL,
            items     TEXT    NOT NULL,
            total     REAL    NOT NULL,
            status    TEXT    NOT NULL DEFAULT 'Paid'
          )
        ''');
      },
    );
  }

  // ── Products ─────────────────────────────────────────────

  Future<List<Product>> getAllProducts() async {
    final db = await database;
    final rows = await db.query('inventory', orderBy: 'item_name');
    print('All products: ${rows.length}');
    return rows.map((r) => Product.fromMap(r)).toList();
  }

  Future<Product?> getProductById(int id) async {
    final db = await database;
    final rows = await db.query('inventory', where: 'id = ?', whereArgs: [id]);
    if (rows.isEmpty) return null;
    return Product.fromMap(rows.first);
  }

  Future<Product?> getProductByName(String name) async {
    final db = await database;
    final rows = await db.query('inventory',
        where: 'LOWER(item_name) = ?', whereArgs: [name.toLowerCase()]);
    if (rows.isEmpty) return null;
    return Product.fromMap(rows.first);
  }

  Future<List<String>> getAllCategories() async {
    final db = await database;
    final rows = await db.rawQuery(
        "SELECT DISTINCT category FROM inventory WHERE category IS NOT NULL AND category != '' ORDER BY category");
    return rows.map((r) => r['category'] as String).toList();
  }

  Future<int> addProduct(Product p) async {
    final db = await database;
    return db.insert('inventory', p.toMap()..remove('id'));
  }

  Future<void> updateProduct(Product p) async {
    final db = await database;
    await db.update('inventory', p.toMap()..remove('id'),
        where: 'id = ?', whereArgs: [p.id]);
  }

  Future<void> updateStock(int productId, int qtySold) async {
    final db = await database;
    await db.rawUpdate(
        'UPDATE inventory SET stock_quantity = stock_quantity - ? WHERE id = ? AND stock_quantity >= ?',
        [qtySold, productId, qtySold]);
  }

  Future<void> deleteProduct(int id) async {
    final db = await database;
    await db.delete('inventory', where: 'id = ?', whereArgs: [id]);
  }

  Future<void> deleteAllProducts() async {
    final db = await database;
    await db.delete('inventory');
    await db.execute("DELETE FROM sqlite_sequence WHERE name='inventory'");
  }

  Future<void> bulkPriceUpdate({
    required bool isIncrease,
    required bool isPercent,
    required double value,
  }) async {
    final db = await database;
    final products = await getAllProducts();
    for (final p in products) {
      double newPrice = p.price;
      if (isPercent) {
        final factor = value / 100.0;
        newPrice = isIncrease
            ? p.price * (1 + factor)
            : p.price * (1 - factor);
      } else {
        newPrice = isIncrease ? p.price + value : p.price - value;
      }
      if (newPrice < 1.0) newPrice = 1.0;
      newPrice = double.parse(newPrice.toStringAsFixed(2));
      await db.update('inventory', {'price': newPrice},
          where: 'id = ?', whereArgs: [p.id]);
    }
  }

  Future<void> replaceAllInventory(List<Product> products) async {
    final db = await database;
    await db.delete('inventory');
    for (final p in products) {
      await db.insert('inventory', p.toMap()..remove('id'));
    }
  }

  // ── Transactions ─────────────────────────────────────────

  Future<int> saveTransaction(String items, double total) async {
    final db = await database;
    final now = DateTime.now().toString().substring(0, 19);
    return db.insert('history', {
      'timestamp': now,
      'items': items,
      'total': total,
      'status': 'Paid',
    });
  }

  Future<List<Map<String, dynamic>>> getTransactionHistory() async {
    final db = await database;
    return db.query('history', orderBy: 'bill_id DESC');
  }

  Future<void> clearHistory() async {
    final db = await database;
    await db.delete('history');
  }
}
