import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../database_helper.dart';
import '../models/product.dart';
import '../models/cart_item.dart';

class ScanScreen extends StatefulWidget {
  final List<CartItem> cart;
  final Function(CartItem) onAddToCart;
  final Function() onCartChanged;

  const ScanScreen({
    super.key,
    required this.cart,
    required this.onAddToCart,
    required this.onCartChanged,
  });

  @override
  State<ScanScreen> createState() => _ScanScreenState();
}

class _ScanScreenState extends State<ScanScreen> {
  final _db = DatabaseHelper();
  final _searchCtrl = TextEditingController();
  final _searchFocus = FocusNode();
  final _picker = ImagePicker();

  Uint8List? _capturedBytes;
  bool _showCaptureResult = false;

  Product? _matchedProduct;
  String? _resultText;
  bool _resultIsError = false;
  List<Product> _searchResults = [];
  int _scanQty = 1;

  @override
  void initState() {
    super.initState();
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  Future<void> _capturePhoto() async {
    try {
      final xfile = await _picker.pickImage(source: ImageSource.camera);
      if (xfile == null) return;
      final bytes = await xfile.readAsBytes();
      if (!mounted) return;
      setState(() {
        _capturedBytes = bytes;
        _showCaptureResult = true;
        _resultText = 'No matching product found';
        _resultIsError = true;
        _matchedProduct = null;
      });
      _searchFocus.requestFocus();
    } catch (e) {
      debugPrint('Capture error: $e');
    }
  }

  Future<void> _pickFromGallery() async {
    try {
      final xfile = await _picker.pickImage(source: ImageSource.gallery);
      if (xfile == null) return;
      final bytes = await xfile.readAsBytes();
      if (!mounted) return;
      setState(() {
        _capturedBytes = bytes;
        _showCaptureResult = true;
        _resultText = 'No matching product found';
        _resultIsError = true;
        _matchedProduct = null;
      });
      _searchFocus.requestFocus();
    } catch (e) {
      debugPrint('Gallery pick error: $e');
    }
  }

  int _cartQtyFor(int pid) {
    int q = 0;
    for (final item in widget.cart) {
      if (item.id == pid) q += item.qty;
    }
    return q;
  }

  void _onSearchChanged(String query) async {
    if (query.trim().isEmpty) {
      setState(() => _searchResults = []);
      return;
    }
    final products = await _db.getAllProducts();
    final q = query.toLowerCase();
    setState(() {
      _searchResults = products
          .where((p) =>
              p.itemName.toLowerCase().contains(q) ||
              p.category.toLowerCase().contains(q))
          .toList();
    });
  }

  void _selectProduct(Product p) {
    setState(() {
      _matchedProduct = p;
      _resultText = 'Selected: ${p.itemName}';
      _resultIsError = false;
      _searchResults = [];
      _scanQty = 1;
    });
    _searchCtrl.text = p.itemName;
  }

  void _addToBill() {
    if (_matchedProduct == null) return;
    final p = _matchedProduct!;
    final cartQty = _cartQtyFor(p.id!);
    if (cartQty >= p.stockQuantity) {
      setState(() {
        _resultText = 'Only ${p.stockQuantity - cartQty} available';
        _resultIsError = true;
      });
      return;
    }
    widget.onAddToCart(CartItem(
        id: p.id!, name: p.itemName, price: p.price, qty: _scanQty));
    widget.onCartChanged();
    setState(() {
      _resultText = '${p.itemName} x$_scanQty added to bill';
      _resultIsError = false;
      _matchedProduct = null;
      _searchCtrl.clear();
      _capturedBytes = null;
      _showCaptureResult = false;
    });
  }

  void _reset() {
    setState(() {
      _capturedBytes = null;
      _showCaptureResult = false;
      _matchedProduct = null;
      _resultText = null;
      _resultIsError = false;
      _searchResults = [];
      _searchCtrl.clear();
      _scanQty = 1;
    });
  }

  Uint8List _base64Decode(String data) {
    try {
      return base64.decode(data.contains(',') ? data.split(',').last : data);
    } catch (_) {
      return Uint8List(0);
    }
  }

  @override
  Widget build(BuildContext context) {
    final maxQty = _matchedProduct != null
        ? _matchedProduct!.stockQuantity - _cartQtyFor(_matchedProduct!.id!)
        : 0;
    return SingleChildScrollView(
      padding: const EdgeInsets.all(12),
      child: Column(
        children: [
          // Heading
          const Text(
            '\u{1F4F7} Scan an item',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          Text(
            'Point your camera at the product barcode or label',
            style: TextStyle(color: Colors.grey.shade600, fontSize: 13),
          ),
          const SizedBox(height: 12),

          // Image capture section
          Container(
            height: 200,
            decoration: BoxDecoration(
              color: Colors.grey.shade100,
              borderRadius: BorderRadius.circular(12),
            ),
            child: const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.camera_alt, size: 48, color: Colors.grey),
                  SizedBox(height: 8),
                  Text('Take a photo or upload an image',
                      style: TextStyle(color: Colors.grey)),
                ],
              ),
            ),
          ),

          const SizedBox(height: 12),

          // "Take a photo of the item" label
          SizedBox(
            width: double.infinity,
            height: 44,
            child: ElevatedButton.icon(
              onPressed: _capturePhoto,
              icon: const Icon(Icons.camera_alt, size: 20),
              label: const Text('Take a photo of the item'),
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.white,
                foregroundColor: Colors.black87,
                side: BorderSide(color: Colors.grey.shade300),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8)),
              ),
            ),
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: SizedBox(
                  height: 44,
                  child: ElevatedButton.icon(
                    onPressed: _pickFromGallery,
                    icon: const Icon(Icons.upload, size: 20),
                    label: const Text('Upload from gallery'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.white,
                      foregroundColor: Colors.black87,
                      side: BorderSide(color: Colors.grey.shade300),
                      shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8)),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              SizedBox(
                height: 44,
                child: ElevatedButton.icon(
                  onPressed: _reset,
                  icon: const Icon(Icons.refresh, size: 20),
                  label: const Text('Reset'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: Colors.black87,
                    side: BorderSide(color: Colors.grey.shade300),
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8)),
                  ),
                ),
              ),
            ],
          ),

          // Captured image preview
          if (_showCaptureResult && _capturedBytes != null)
            Container(
              margin: const EdgeInsets.only(top: 12),
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.grey.shade50,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: Colors.grey.shade200),
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.memory(
                  _capturedBytes!,
                  height: 120,
                  fit: BoxFit.cover,
                  width: double.infinity,
                ),
              ),
            ),

          // Result message (inline, not snackbar)
          if (_resultText != null && !_showCaptureResult)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(10),
              margin: const EdgeInsets.only(top: 12),
              decoration: BoxDecoration(
                color: _resultIsError
                    ? Colors.red.shade50
                    : Colors.green.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: _resultIsError
                      ? Colors.red.shade200
                      : Colors.green.shade200,
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    _resultIsError
                        ? Icons.error_outline
                        : Icons.check_circle,
                    color: _resultIsError ? Colors.red : Colors.green,
                    size: 20,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(_resultText!,
                        style: const TextStyle(fontSize: 14)),
                  ),
                ],
              ),
            ),

          // Matched product card
          if (_matchedProduct != null) ...[
            const SizedBox(height: 12),
            Card(
              elevation: 1,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10)),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Row(
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: Container(
                        width: 80,
                        height: 80,
                        color: Colors.grey.shade100,
                        child: _matchedProduct!.imageData != null
                            ? Image.memory(
                                _base64Decode(_matchedProduct!.imageData!),
                                fit: BoxFit.cover,
                                errorBuilder: (_, _, _) =>
                                    const Icon(Icons.image, size: 36),
                              )
                            : const Icon(Icons.image, size: 36,
                                color: Colors.grey),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(_matchedProduct!.itemName,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w600, fontSize: 16)),
                          const SizedBox(height: 2),
                          Text(_matchedProduct!.category,
                              style: TextStyle(
                                  color: Colors.grey.shade600, fontSize: 12)),
                          const SizedBox(height: 4),
                          Text(
                            '\u20B9${_matchedProduct!.price.toStringAsFixed(2)}',
                            style: const TextStyle(
                                fontSize: 20,
                                fontWeight: FontWeight.bold,
                                color: Color(0xFFE53935)),
                          ),
                          Text(
                            'Stock: ${_matchedProduct!.stockQuantity}',
                            style: TextStyle(
                                color: Colors.grey.shade600, fontSize: 13),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 8),
            if (maxQty > 0) ...[
              Row(
                children: [
                  const Text('Quantity: ',
                      style: TextStyle(fontWeight: FontWeight.w500)),
                  IconButton(
                    icon: const Icon(Icons.remove_circle_outline),
                    onPressed: _scanQty > 1
                        ? () => setState(() => _scanQty--)
                        : null,
                  ),
                  Text('$_scanQty',
                      style: const TextStyle(
                          fontSize: 18, fontWeight: FontWeight.bold)),
                  IconButton(
                    icon: const Icon(Icons.add_circle_outline),
                    onPressed: _scanQty < maxQty
                        ? () => setState(() => _scanQty++)
                        : null,
                  ),
                  Text('(max $maxQty)',
                      style: TextStyle(
                          color: Colors.grey.shade500, fontSize: 12)),
                ],
              ),
              const SizedBox(height: 4),
              SizedBox(
                width: double.infinity,
                height: 44,
                child: ElevatedButton.icon(
                  onPressed: _addToBill,
                  icon: const Icon(Icons.add_shopping_cart, size: 20),
                  label: Text('Add to Bill (\u20B9${(_matchedProduct!.price * _scanQty).toStringAsFixed(2)})'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFFE53935),
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8)),
                  ),
                ),
              ),
            ] else
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: Colors.red.shade50,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Text('OUT OF STOCK',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        color: Colors.red,
                        fontWeight: FontWeight.bold,
                        fontSize: 16)),
              ),
          ],

          const SizedBox(height: 16),

          // Always-visible search section
          TextField(
            controller: _searchCtrl,
            focusNode: _searchFocus,
            decoration: InputDecoration(
              hintText: 'Search item...',
              prefixIcon: const Icon(Icons.search, color: Colors.grey),
              border:
                  OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
            ),
            onChanged: _onSearchChanged,
          ),
          const SizedBox(height: 8),
          if (_searchCtrl.text.isNotEmpty && _searchResults.isEmpty)
            Padding(
              padding: const EdgeInsets.all(8),
              child: Text('No products found',
                  style: TextStyle(color: Colors.grey.shade600)),
            ),
          ..._searchResults.map((p) => Card(
                margin: const EdgeInsets.only(bottom: 4),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8)),
                child: ListTile(
                  dense: true,
                  leading: p.imageData != null
                      ? ClipRRect(
                          borderRadius: BorderRadius.circular(4),
                          child: Image.memory(
                            _base64Decode(p.imageData!),
                            width: 44,
                            height: 44,
                            fit: BoxFit.cover,
                            errorBuilder: (_, _, _) =>
                                const Icon(Icons.image, size: 24),
                          ),
                        )
                      : const Icon(Icons.image, size: 24, color: Colors.grey),
                  title: Text(p.itemName,
                      style: const TextStyle(
                          fontWeight: FontWeight.w500, fontSize: 14)),
                  subtitle: Text(
                      '\u20B9${p.price.toStringAsFixed(2)}  Stock: ${p.stockQuantity}',
                      style: TextStyle(
                          color: Colors.grey.shade600, fontSize: 12)),
                  onTap: () => _selectProduct(p),
                ),
              )),
        ],
      ),
    );
  }
}
