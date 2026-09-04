#include "base.hpp"

class Circle : public Shape {
 public:
  double area() override { return 3.14; }
};
