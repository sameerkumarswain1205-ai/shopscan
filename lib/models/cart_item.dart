class CartItem {
  final int id;
  final String name;
  final double price;
  int qty;

  CartItem({
    required this.id,
    required this.name,
    required this.price,
    required this.qty,
  });

  Map<String, dynamic> toMap() => {
        'id': id,
        'name': name,
        'price': price,
        'qty': qty,
      };
}
