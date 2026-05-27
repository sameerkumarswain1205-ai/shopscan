import 'package:flutter/material.dart';
import 'models/cart_item.dart';
import 'screens/scan_screen.dart';
import 'screens/bill_screen.dart';
import 'screens/admin_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ShopScanApp());
}

class ShopScanApp extends StatefulWidget {
  const ShopScanApp({super.key});

  @override
  State<ShopScanApp> createState() => _ShopScanAppState();
}

class _ShopScanAppState extends State<ShopScanApp> with TickerProviderStateMixin {
  late final TabController _tabCtrl;
  final List<CartItem> _cart = [];
  int _cartVersion = 0;

  void _onAddToCart(CartItem item) {
    final existing = _cart.where((c) => c.id == item.id).firstOrNull;
    if (existing != null) {
      existing.qty += item.qty;
    } else {
      _cart.add(item);
    }
  }

  void _onQtyChanged(int index, int newQty) {
    _cart[index].qty = newQty;
  }

  void _onRemoveItem(int index) {
    _cart.removeAt(index);
  }

  void _onClearCart() {
    _cart.clear();
  }

  void _onCartChanged() {
    setState(() => _cartVersion++);
  }

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 3, vsync: this);
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'ShopScan',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        scaffoldBackgroundColor: Colors.white,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFE53935),
          brightness: Brightness.light,
          primary: const Color(0xFFE53935),
          onPrimary: Colors.white,
        ),
        useMaterial3: true,
        appBarTheme: const AppBarTheme(
          backgroundColor: Colors.white,
          foregroundColor: Color(0xFF212121),
          elevation: 0.5,
          centerTitle: true,
        ),
        tabBarTheme: const TabBarThemeData(
          labelColor: Color(0xFFE53935),
          unselectedLabelColor: Color(0xFF757575),
          indicatorColor: Color(0xFFE53935),
        ),
      ),
      home: DefaultTabController(
        length: 3,
        child: Scaffold(
          appBar: AppBar(
            title: const Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text('\u{1F50C}', style: TextStyle(fontSize: 24)),
                SizedBox(width: 6),
                Text('ShopScan',
                    style: TextStyle(fontWeight: FontWeight.bold, fontSize: 22)),
              ],
            ),
            bottom: const TabBar(
              tabs: [
                Tab(text: 'Scan & Sell'),
                Tab(text: 'Current Bill'),
                Tab(text: 'Inventory Admin'),
              ],
            ),
            backgroundColor: Colors.white,
            foregroundColor: const Color(0xFF212121),
            elevation: 0.5,
          ),
          body: TabBarView(
            children: [
              ScanScreen(
                key: ValueKey('scan_$_cartVersion'),
                cart: _cart,
                onAddToCart: _onAddToCart,
                onCartChanged: _onCartChanged,
              ),
              BillScreen(
                key: ValueKey('bill_$_cartVersion'),
                cart: _cart,
                onQtyChanged: _onQtyChanged,
                onRemoveItem: _onRemoveItem,
                onClearCart: _onClearCart,
                onCartChanged: _onCartChanged,
              ),
              const AdminScreen(),
            ],
          ),
        ),
      ),
    );
  }
}
