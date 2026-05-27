import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:csv/csv.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import '../database_helper.dart';
import '../models/product.dart';

class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen>
    with SingleTickerProviderStateMixin {
  final _db = DatabaseHelper();
  late TabController _tabCtrl;

  // Add product form
  final _nameCtrl = TextEditingController();
  final _categoryCtrl = TextEditingController();
  final _priceCtrl = TextEditingController();
  final _stockCtrl = TextEditingController();
  List<String> _categories = [];

  // Stock view
  List<Product> _products = [];
  List<Product> _filteredProducts = [];
  final _searchCtrl = TextEditingController();
  String _stockSortBy = 'name';

  // History
  List<Map<String, dynamic>> _history = [];

  // Bulk update
  bool _bulkIsIncrease = true;
  bool _bulkIsPercent = true;
  final _bulkValueCtrl = TextEditingController();

  // Edit dialog
  final _editNameCtrl = TextEditingController();
  final _editCategoryCtrl = TextEditingController();
  final _editPriceCtrl = TextEditingController();
  final _editStockCtrl = TextEditingController();

  // Delete all
  bool _confirmDeleteAll = false;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 3, vsync: this);
    _tabCtrl.addListener(() {
      if (!_tabCtrl.indexIsChanging) _refresh();
    });
    _refresh();
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    _nameCtrl.dispose();
    _categoryCtrl.dispose();
    _priceCtrl.dispose();
    _stockCtrl.dispose();
    _searchCtrl.dispose();
    _bulkValueCtrl.dispose();
    _editNameCtrl.dispose();
    _editCategoryCtrl.dispose();
    _editPriceCtrl.dispose();
    _editStockCtrl.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    final categories = await _db.getAllCategories();
    final products = await _db.getAllProducts();
    final history = await _db.getTransactionHistory();
    if (mounted) {
      setState(() {
        _categories = categories;
        _products = products;
        _filteredProducts = _filterProducts(products);
        _history = history;
      });
    }
  }

  List<Product> _filterProducts(List<Product> products) {
    final q = _searchCtrl.text.toLowerCase();
    if (q.isEmpty) return products;
    return products
        .where((p) =>
            p.itemName.toLowerCase().contains(q) ||
            p.category.toLowerCase().contains(q))
        .toList();
  }

  void _onSearchChanged() {
    setState(() => _filteredProducts = _filterProducts(_products));
  }

  // ── Add Product Tab ────────────────────────────────────

  Future<void> _saveProduct() async {
    final name = _nameCtrl.text.trim();
    if (name.isEmpty) {
      _showMsg('Item name is required');
      return;
    }
    final price = double.tryParse(_priceCtrl.text.trim());
    if (price == null || price <= 0) {
      _showMsg('Price must be > 0');
      return;
    }
    final stock = int.tryParse(_stockCtrl.text.trim()) ?? 0;
    final category = _categoryCtrl.text.trim().isEmpty ? 'General' : _categoryCtrl.text.trim();

    await _db.addProduct(Product(
      itemName: name,
      category: category,
      price: price,
      stockQuantity: stock,
    ));

    _nameCtrl.clear();
    _priceCtrl.clear();
    _stockCtrl.clear();
    _categoryCtrl.clear();
    if (mounted) {
      _showMsg('Product added successfully!');
      _refresh();
    }
  }

  // ── Stock Tab ──────────────────────────────────────────

  void _showEditDialog(Product p) {
    _editNameCtrl.text = p.itemName;
    _editCategoryCtrl.text = p.category;
    _editPriceCtrl.text = p.price.toStringAsFixed(2);
    _editStockCtrl.text = p.stockQuantity.toString();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit Product'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                  controller: _editNameCtrl,
                  decoration: const InputDecoration(labelText: 'Name')),
              TextField(
                  controller: _editCategoryCtrl,
                  decoration: const InputDecoration(labelText: 'Category')),
              TextField(
                  controller: _editPriceCtrl,
                  decoration: const InputDecoration(labelText: 'Price'),
                  keyboardType: TextInputType.number),
              TextField(
                  controller: _editStockCtrl,
                  decoration: const InputDecoration(labelText: 'Stock'),
                  keyboardType: TextInputType.number),
            ],
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel')),
          ElevatedButton(
            onPressed: () async {
              final name = _editNameCtrl.text.trim();
              if (name.isEmpty) return;
              final price = double.tryParse(_editPriceCtrl.text.trim()) ?? p.price;
              final stock = int.tryParse(_editStockCtrl.text.trim()) ?? p.stockQuantity;
              final cat = _editCategoryCtrl.text.trim().isEmpty ? 'General' : _editCategoryCtrl.text.trim();
              await _db.updateProduct(p.copyWith(
                itemName: name,
                category: cat,
                price: price,
                stockQuantity: stock,
              ));
              if (ctx.mounted) Navigator.pop(ctx);
              _refresh();
              _showMsg('Product updated');
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }

  void _showDeleteConfirm(Product p) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete Product'),
        content: Text('Delete "${p.itemName}"?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel')),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red, foregroundColor: Colors.white),
            onPressed: () async {
              await _db.deleteProduct(p.id!);
              if (ctx.mounted) Navigator.pop(ctx);
              _refresh();
              _showMsg('Product deleted');
            },
            child: const Text('Delete'),
          ),
        ],
      ),
    );
  }

  Future<void> _exportInventoryCSV() async {
    final products = await _db.getAllProducts();
    final rows = <List<dynamic>>[
      ['id', 'item_name', 'category', 'price', 'stock_quantity', 'image_path'],
      ...products.map((p) => <dynamic>[
            p.id.toString(),
            p.itemName,
            p.category,
            p.price.toStringAsFixed(2),
            p.stockQuantity.toString(),
            p.imagePath ?? '',
          ]),
    ];
    final csv = const ListToCsvConverter().convert(rows);
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/inventory_backup.csv');
    await file.writeAsString(csv);
    await Share.shareXFiles([XFile(file.path)], text: 'Inventory Backup');
  }

  Future<void> _importInventoryCSV() async {
    // For simplicity, show how to import via clipboard or file picker
    _showMsg('Import: copy CSV content and use database import tool');
  }

  void _showBulkUpdateDialog() {
    showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDState) => AlertDialog(
          title: const Text('Bulk Price Update'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  ChoiceChip(
                      label: const Text('Increase'),
                      selected: _bulkIsIncrease,
                      onSelected: (v) => setDState(() => _bulkIsIncrease = v)),
                  const SizedBox(width: 8),
                  ChoiceChip(
                      label: const Text('Decrease'),
                      selected: !_bulkIsIncrease,
                      onSelected: (v) => setDState(() => _bulkIsIncrease = !v)),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  ChoiceChip(
                      label: const Text('%'),
                      selected: _bulkIsPercent,
                      onSelected: (v) => setDState(() => _bulkIsPercent = v)),
                  const SizedBox(width: 8),
                  ChoiceChip(
                      label: const Text('₹'),
                      selected: !_bulkIsPercent,
                      onSelected: (v) => setDState(() => _bulkIsPercent = !v)),
                ],
              ),
              const SizedBox(height: 8),
              TextField(
                controller: _bulkValueCtrl,
                decoration: const InputDecoration(
                    labelText: 'Value', border: OutlineInputBorder()),
                keyboardType: TextInputType.number,
              ),
            ],
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('Cancel')),
            ElevatedButton(
              onPressed: () async {
                final val = double.tryParse(_bulkValueCtrl.text.trim());
                if (val == null || val <= 0) return;
                await _db.bulkPriceUpdate(
                  isIncrease: _bulkIsIncrease,
                  isPercent: _bulkIsPercent,
                  value: val,
                );
                if (ctx.mounted) Navigator.pop(ctx);
                _refresh();
                _showMsg('Prices updated');
              },
              child: const Text('Apply'),
            ),
          ],
        ),
      ),
    );
  }

  void _showDeleteAllConfirm() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete All Products'),
        content: const Text('This will delete ALL products. Are you sure?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel')),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red, foregroundColor: Colors.white),
            onPressed: () async {
              await _db.deleteAllProducts();
              if (ctx.mounted) Navigator.pop(ctx);
              _refresh();
              _showMsg('All products deleted');
            },
            child: const Text('Delete All'),
          ),
        ],
      ),
    );
  }

  // ── History Tab ────────────────────────────────────────

  Future<void> _exportSalesCSV() async {
    final history = await _db.getTransactionHistory();
    final rows = <List<dynamic>>[
      ['S.No', 'Bill ID', 'Date', 'Time', 'Item Name', 'Quantity', 'Total Amount', 'Status'],
    ];
    for (int i = 0; i < history.length; i++) {
      final h = history[i];
      final ts = h['timestamp'] as String? ?? '';
      final date = ts.length >= 10 ? ts.substring(0, 10) : ts;
      final time = ts.length > 11 ? ts.substring(11, 19) : '';
      final itemsStr = h['items'] as String? ?? '';
      // Split items for CSV rows
      final itemParts = itemsStr.split(', ');
      if (itemParts.isEmpty || (itemParts.length == 1 && itemParts[0].isEmpty)) {
        rows.add([
          '${i + 1}',
          h['bill_id'].toString(),
          date,
          time,
          '',
          '',
          '₹${(h['total'] as num).toStringAsFixed(2)}',
          h['status'] as String? ?? '',
        ]);
      } else {
        for (final part in itemParts) {
          final idx = part.lastIndexOf(' x');
          final itemName = idx >= 0 ? part.substring(0, idx) : part;
          final qty = idx >= 0 ? part.substring(idx + 2) : '1';
          rows.add([
            '${i + 1}',
            h['bill_id'].toString(),
            date,
            time,
            itemName,
            qty,
            '₹${(h['total'] as num).toStringAsFixed(2)}',
            h['status'] as String? ?? '',
          ]);
        }
      }
    }
    final csv = const ListToCsvConverter().convert(rows);
    final dir = await getTemporaryDirectory();
    final file = File('${dir.path}/sales_history.csv');
    await file.writeAsString(csv);
    await Share.shareXFiles([XFile(file.path)], text: 'Sales History');
  }

  void _showClearHistoryConfirm() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Clear History'),
        content: const Text('Delete all sales history?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel')),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red, foregroundColor: Colors.white),
            onPressed: () async {
              await _db.clearHistory();
              if (ctx.mounted) Navigator.pop(ctx);
              _refresh();
              _showMsg('History cleared');
            },
            child: const Text('Clear'),
          ),
        ],
      ),
    );
  }

  // ── Helpers ────────────────────────────────────────────

  void _showMsg(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(msg), duration: const Duration(seconds: 2)));
  }

  String _formatDate(String? ts) {
    if (ts == null || ts.length < 10) return '';
    return ts.substring(0, 10);
  }

  String _formatTime(String? ts) {
    if (ts == null || ts.length < 19) return '';
    return ts.substring(11, 19);
  }

  Uint8List _base64ToBytes(String data) {
    try {
      final s = data.contains(',') ? data.split(',').last : data;
      return base64.decode(s);
    } catch (_) {
      return Uint8List(0);
    }
  }

  // ── Build ──────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        TabBar(
          controller: _tabCtrl,
          labelColor: Colors.orange,
          unselectedLabelColor: Colors.grey,
          tabs: const [
            Tab(text: 'Add Product', icon: Icon(Icons.add_box, size: 20)),
            Tab(text: 'Stock', icon: Icon(Icons.inventory, size: 20)),
            Tab(text: 'History', icon: Icon(Icons.history, size: 20)),
          ],
        ),
        Expanded(
          child: TabBarView(
            controller: _tabCtrl,
            children: [
              _buildAddProductTab(),
              _buildStockTab(),
              _buildHistoryTab(),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildAddProductTab() {
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        TextField(
          controller: _nameCtrl,
          decoration: const InputDecoration(labelText: 'Item Name *', border: OutlineInputBorder()),
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: DropdownButtonFormField<String>(
                value: _categories.isNotEmpty ? _categories.first : null,
                decoration: const InputDecoration(labelText: 'Category', border: OutlineInputBorder()),
                items: _categories
                    .map((c) => DropdownMenuItem(value: c, child: Text(c)))
                    .toList(),
                onChanged: (v) {
                  if (v != null) _categoryCtrl.text = v;
                },
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: TextField(
                controller: _categoryCtrl,
                decoration: const InputDecoration(labelText: 'Or type new', border: OutlineInputBorder()),
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _priceCtrl,
                decoration: const InputDecoration(labelText: 'Price (₹) *', border: OutlineInputBorder()),
                keyboardType: TextInputType.number,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                controller: _stockCtrl,
                decoration: const InputDecoration(labelText: 'Stock', border: OutlineInputBorder()),
                keyboardType: TextInputType.number,
              ),
            ),
          ],
        ),
        const SizedBox(height: 16),
        SizedBox(
          width: double.infinity,
          height: 44,
          child: ElevatedButton.icon(
            onPressed: _saveProduct,
            icon: const Icon(Icons.save),
            label: const Text('Save Product'),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.green,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildStockTab() {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(8),
          child: TextField(
            controller: _searchCtrl,
            decoration: InputDecoration(
              hintText: 'Search by name or category...',
              prefixIcon: const Icon(Icons.search),
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
              contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            ),
            onChanged: (_) => _onSearchChanged(),
          ),
        ),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: Row(
            children: [
              TextButton.icon(
                icon: const Icon(Icons.download, size: 18),
                label: const Text('Export CSV'),
                onPressed: _exportInventoryCSV,
              ),
              const Spacer(),
              TextButton.icon(
                icon: const Icon(Icons.trending_up, size: 18),
                label: const Text('Bulk Price'),
                onPressed: _showBulkUpdateDialog,
              ),
              TextButton.icon(
                icon: const Icon(Icons.delete_sweep, size: 18),
                label: const Text('Delete All'),
                onPressed: _showDeleteAllConfirm,
              ),
            ],
          ),
        ),
        Expanded(
          child: _filteredProducts.isEmpty
              ? Center(
                  child: Text('No products found',
                      style: TextStyle(color: Colors.grey.shade500)))
              : RefreshIndicator(
                  onRefresh: _refresh,
                  child: ListView.builder(
                    itemCount: _filteredProducts.length,
                    itemBuilder: (_, i) {
                      final p = _filteredProducts[i];
                      return Card(
                        margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        child: ListTile(
                          leading: p.imageData != null
                              ? ClipRRect(
                                  borderRadius: BorderRadius.circular(4),
                                  child: Image.memory(
                                    _base64ToBytes(p.imageData!),
                                    width: 48,
                                    height: 48,
                                    fit: BoxFit.cover,
                                    errorBuilder: (_, __, ___) =>
                                        const Icon(Icons.image, size: 28),
                                  ),
                                )
                              : Container(
                                  width: 48,
                                  height: 48,
                                  decoration: BoxDecoration(
                                    color: Colors.grey.shade100,
                                    borderRadius: BorderRadius.circular(4),
                                  ),
                                  child: const Icon(Icons.image,
                                      size: 28, color: Colors.grey),
                                ),
                          title: Text(p.itemName,
                              style: const TextStyle(fontWeight: FontWeight.w600)),
                          subtitle: Text(
                            '₹${p.price.toStringAsFixed(2)}  |  Stock: ${p.stockQuantity}  |  ${p.category}',
                            style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
                          ),
                          trailing: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              IconButton(
                                icon: const Icon(Icons.edit, size: 20),
                                onPressed: () => _showEditDialog(p),
                              ),
                              IconButton(
                                icon: const Icon(Icons.delete, size: 20, color: Colors.red),
                                onPressed: () => _showDeleteConfirm(p),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
        ),
      ],
    );
  }

  Widget _buildHistoryTab() {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          child: Row(
            children: [
              TextButton.icon(
                icon: const Icon(Icons.download, size: 18),
                label: const Text('Export CSV'),
                onPressed: _exportSalesCSV,
              ),
              const Spacer(),
              TextButton.icon(
                icon: const Icon(Icons.delete_sweep, size: 18),
                label: const Text('Clear'),
                onPressed: _showClearHistoryConfirm,
              ),
            ],
          ),
        ),
        Expanded(
          child: _history.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.receipt_long_outlined,
                          size: 48, color: Colors.grey.shade300),
                      const SizedBox(height: 8),
                      Text('No sales yet',
                          style: TextStyle(color: Colors.grey.shade500)),
                    ],
                  ),
                )
              : ListView.builder(
                  itemCount: _history.length,
                  itemBuilder: (_, i) {
                    final h = _history[i];
                    return Card(
                      margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      child: ListTile(
                        leading: CircleAvatar(
                          backgroundColor: Colors.green.shade50,
                          child: Text('${h['bill_id']}',
                              style: const TextStyle(
                                  fontWeight: FontWeight.bold)),
                        ),
                        title: Text(h['items'] as String? ?? '',
                            maxLines: 1, overflow: TextOverflow.ellipsis),
                        subtitle: Text(
                          '${_formatDate(h['timestamp'] as String?)}  ${_formatTime(h['timestamp'] as String?)}',
                          style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
                        ),
                        trailing: Text(
                          '₹${(h['total'] as num).toStringAsFixed(2)}',
                          style: const TextStyle(
                              fontWeight: FontWeight.bold, fontSize: 15),
                        ),
                      ),
                    );
                  },
                ),
        ),
      ],
    );
  }
}
