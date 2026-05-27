import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../database_helper.dart';
import '../models/cart_item.dart';

class BillScreen extends StatefulWidget {
  final List<CartItem> cart;
  final Function(int index, int newQty) onQtyChanged;
  final Function(int index) onRemoveItem;
  final VoidCallback onClearCart;
  final VoidCallback onCartChanged;

  const BillScreen({
    super.key,
    required this.cart,
    required this.onQtyChanged,
    required this.onRemoveItem,
    required this.onClearCart,
    required this.onCartChanged,
  });

  @override
  State<BillScreen> createState() => _BillScreenState();
}

class _BillScreenState extends State<BillScreen> {
  final _db = DatabaseHelper();
  bool _isCheckingOut = false;
  String? _receiptHtml;

  double get _grandTotal {
    double total = 0;
    for (final item in widget.cart) {
      total += item.price * item.qty;
    }
    return total;
  }

  Future<void> _checkout() async {
    if (widget.cart.isEmpty) return;
    setState(() => _isCheckingOut = true);

    final db = DatabaseHelper();
    final List<String> failures = [];

    // Verify stock for each item
    for (final item in widget.cart) {
      final prod = await db.getProductById(item.id);
      if (prod == null) {
        failures.add('${item.name}: product not found');
      } else if (prod.stockQuantity < item.qty) {
        failures.add(
            '${item.name}: only ${prod.stockQuantity} in stock, need ${item.qty}');
      }
    }

    if (failures.isNotEmpty) {
      if (mounted) {
        showDialog(
          context: context,
          builder: (_) => AlertDialog(
            title: const Text('Stock Error'),
            content: Text(failures.join('\n')),
            actions: [
              TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('OK'))
            ],
          ),
        );
        setState(() => _isCheckingOut = false);
      }
      return;
    }

    // Deduct stock
    for (final item in widget.cart) {
      await db.updateStock(item.id, item.qty);
    }

    // Build items string
    final itemsStr = widget.cart.map((i) => '${i.name} x${i.qty}').join(', ');
    final total = _grandTotal;

    await db.saveTransaction(itemsStr, total);

    final now = DateTime.now();
    final dateStr = DateFormat('dd-MMM-yyyy hh:mm a').format(now);

    // Build receipt
    final receipt = '''
ShopScan Receipt
----------------
$dateStr

Item          Qty     Amount
${widget.cart.map((i) => '${i.name.padRight(12)} ${i.qty.toString().padLeft(3)}     ₹${(i.price * i.qty).toStringAsFixed(2)}').join('\n')}

Total: ₹${total.toStringAsFixed(2)}
----------------
Thank you for your purchase!
''';

    if (mounted) {
      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.receipt, color: Colors.green),
              SizedBox(width: 8),
              Text('Receipt'),
            ],
          ),
          content: SingleChildScrollView(
            child: SelectableText(receipt, style: const TextStyle(fontFamily: 'monospace', fontSize: 13)),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.pop(ctx);
                widget.onClearCart();
                widget.onCartChanged();
              },
              child: const Text('Done'),
            ),
          ],
        ),
      );
    }

    setState(() => _isCheckingOut = false);
  }

  @override
  Widget build(BuildContext context) {
    if (widget.cart.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.shopping_cart_outlined, size: 64, color: Colors.grey.shade300),
            const SizedBox(height: 16),
            Text('Cart is empty', style: TextStyle(color: Colors.grey.shade600, fontSize: 16)),
            const SizedBox(height: 8),
            Text('Scan or search products to add them',
                style: TextStyle(color: Colors.grey.shade400)),
          ],
        ),
      );
    }

    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: widget.cart.length,
            itemBuilder: (_, i) {
              final item = widget.cart[i];
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: Padding(
                  padding: const EdgeInsets.all(10),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(item.name,
                                style: const TextStyle(
                                    fontWeight: FontWeight.w600, fontSize: 15)),
                            const SizedBox(height: 4),
                            Text('₹${item.price.toStringAsFixed(2)}',
                                style: TextStyle(color: Colors.grey.shade600)),
                          ],
                        ),
                      ),
                      Row(
                        children: [
                          Container(
                            width: 60,
                            height: 36,
                            decoration: BoxDecoration(
                              border: Border.all(color: Colors.grey.shade300),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Center(
                              child: Text('${item.qty}',
                                  style: const TextStyle(fontSize: 15)),
                            ),
                          ),
                          const SizedBox(width: 4),
                          Column(
                            children: [
                              InkWell(
                                onTap: () {
                                  widget.onQtyChanged(i, item.qty + 1);
                                  widget.onCartChanged();
                                },
                                child: const Icon(Icons.add_circle_outline,
                                    size: 22, color: Colors.green),
                              ),
                              InkWell(
                                onTap: () {
                                  if (item.qty > 1) {
                                    widget.onQtyChanged(i, item.qty - 1);
                                    widget.onCartChanged();
                                  }
                                },
                                child: const Icon(Icons.remove_circle_outline,
                                    size: 22, color: Colors.red),
                              ),
                            ],
                          ),
                          const SizedBox(width: 8),
                          Text('₹${(item.price * item.qty).toStringAsFixed(2)}',
                              style:
                                  const TextStyle(fontWeight: FontWeight.w600)),
                          const SizedBox(width: 8),
                          InkWell(
                            onTap: () {
                              widget.onRemoveItem(i);
                              widget.onCartChanged();
                            },
                            child: const Icon(Icons.delete_outline,
                                color: Colors.red, size: 22),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),

        // Bottom bar
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white,
            boxShadow: [
              BoxShadow(
                  color: Colors.grey.shade200, blurRadius: 4, offset: const Offset(0, -2)),
            ],
          ),
          child: SafeArea(
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Total',
                          style: TextStyle(color: Colors.grey.shade600, fontSize: 13)),
                      Text(
                        '₹${_grandTotal.toStringAsFixed(2)}',
                        style: const TextStyle(
                            fontSize: 20, fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                OutlinedButton(
                  onPressed: () {
                    widget.onClearCart();
                    widget.onCartChanged();
                  },
                  child: const Text('Clear'),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: _isCheckingOut ? null : _checkout,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.green,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
                  ),
                  child: _isCheckingOut
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white),
                        )
                      : const Text('Confirm Bill'),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
